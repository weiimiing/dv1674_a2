#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
blur_dir="${BLUR_DIR:-$repo_root/versions/parallel/blur}"
reference_dir="${BLUR_REFERENCE_DIR:-$repo_root/results/reference/blur}"
results_dir="${BLUR_RESULTS_DIR:-${RESULTS_DIR:-$repo_root/results/profiling/parallel_blur}}"

read -r -a image_names <<< "${IMAGES:-im1 im2 im3 im4}"
radius="${BLUR_RADIUS:-15}"

if [[ ! "$radius" =~ ^[0-9]+$ ]]; then
    echo "Error: BLUR_RADIUS must be a non-negative integer." >&2
    exit 1
fi

if [[ -n "${THREAD_COUNTS:-}" ]]; then
    read -r -a thread_counts <<< "$THREAD_COUNTS"
elif [[ -n "${MAX_THREADS:-}" ]]; then
    if [[ ! "$MAX_THREADS" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: MAX_THREADS must be a positive integer." >&2
        exit 1
    fi

    thread_counts=(1)
    next_thread_count=2
    while ((next_thread_count <= MAX_THREADS)); do
        thread_counts+=("$next_thread_count")
        next_thread_count=$((next_thread_count * 2))
    done

    last_index=$((${#thread_counts[@]} - 1))
    if ((thread_counts[last_index] != MAX_THREADS)); then
        thread_counts+=("$MAX_THREADS")
    fi
else
    thread_counts=(1 2 4 8 16 32)
fi

highest_thread_count=1
for thread_count in "${thread_counts[@]}"; do
    if [[ ! "$thread_count" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: every THREAD_COUNTS value must be a positive integer." >&2
        exit 1
    fi
    if ((thread_count > highest_thread_count)); then
        highest_thread_count="$thread_count"
    fi
done

if ((highest_thread_count == 1)); then
    default_profiler_threads="1"
else
    default_profiler_threads="1 $highest_thread_count"
fi

read -r -a gprof_threads <<< "${GPROF_THREADS:-$default_profiler_threads}"
read -r -a callgrind_threads <<< "${CALLGRIND_THREADS:-$default_profiler_threads}"

temp_dir="$(mktemp -d /tmp/a2-parallel-blur.XXXXXX)"

batches="${BATCHES:-5}"
pause_seconds="${PAUSE_SECONDS:-1}"
target_batch_seconds="${TARGET_BATCH_SECONDS:-2}"
max_batch_iterations="${MAX_BATCH_ITERATIONS:-100000}"

run_gprof="${RUN_GPROF:-1}"
run_callgrind="${RUN_CALLGRIND:-1}"
run_helgrind="${RUN_HELGRIND:-1}"

gprof_image="${GPROF_IMAGE:-im4}"
callgrind_image="${CALLGRIND_IMAGE:-im2}"
helgrind_image="${HELGRIND_IMAGE:-im1}"
helgrind_threads="${HELGRIND_THREADS:-$highest_thread_count}"

timing_raw="$results_dir/timing_raw.csv"
memory_raw="$results_dir/memory_raw.csv"
correctness_raw="$results_dir/correctness.csv"
summary_file="$results_dir/summary.csv"
correctness_log="$results_dir/correctness_details.txt"
callgrind_metrics="$results_dir/callgrind_metrics.csv"
helgrind_summary="$results_dir/helgrind_status.txt"

instrumented_build=0

restore_normal_build()
{
    echo "Restoring the normal -O2 pthread build..."
    make -C "$blur_dir" clean
    make -C "$blur_dir"
    instrumented_build=0
}

cleanup()
{
    local status=$?
    trap - EXIT
    set +e
    rm -rf -- "$temp_dir"
    if ((instrumented_build)); then
        restore_normal_build > /dev/null 2>&1
    fi
    exit "$status"
}

trap cleanup EXIT

require_command()
{
    local command_name="$1"
    if ! command -v "$command_name" > /dev/null 2>&1; then
        echo "Error: required command '$command_name' is not installed." >&2
        exit 1
    fi
}

for command_name in make awk sort cmp; do
    require_command "$command_name"
done

if [[ ! -x /usr/bin/time ]]; then
    echo "Error: GNU time was not found at /usr/bin/time." >&2
    exit 1
fi

if [[ "$run_gprof" == "1" ]]; then
    require_command gprof
fi

if [[ "$run_callgrind" == "1" ]]; then
    require_command valgrind
    require_command callgrind_annotate
fi

if [[ "$run_helgrind" == "1" ]]; then
    require_command valgrind
fi

if [[ ! -d "$blur_dir" ]]; then
    echo "Error: parallel Blur directory does not exist: $blur_dir" >&2
    exit 1
fi

if ((${#image_names[@]} == 0)); then
    echo "Error: IMAGES must contain at least one image name." >&2
    exit 1
fi

mkdir -p "$results_dir"
: > "$correctness_log"

printf "program,input,threads,batch,iterations,total_elapsed_seconds,user_seconds,system_seconds\n" \
    > "$timing_raw"
printf "program,input,threads,max_rss_kb,direct_elapsed_seconds,user_seconds,system_seconds\n" \
    > "$memory_raw"
printf "program,input,threads,status\n" > "$correctness_raw"

echo "Building parallel Blur..."
restore_normal_build

blur_executable="$blur_dir/blur_par"

if [[ ! -x "$blur_executable" ]]; then
    echo "Error: Makefile did not create $blur_executable" >&2
    exit 1
fi

initial_iterations_for_image()
{
    case "$1" in
        im1) echo 10 ;;
        im2) echo 5 ;;
        im3) echo 2 ;;
        im4) echo 1 ;;
        *) echo 1 ;;
    esac
}

calibrate_iterations()
{
    local initial_iterations="$1"
    local executable="$2"
    local input="$3"
    local output="$4"
    local threads="$5"
    local iterations="$initial_iterations"
    local elapsed

    if ((iterations > max_batch_iterations)); then
        iterations="$max_batch_iterations"
    fi

    while true; do
        /usr/bin/time -f "%e" -o "$temp_dir/calibration.time" \
            bash -c '
                set -e
                iterations=$1
                executable=$2
                radius=$3
                input=$4
                output=$5
                threads=$6
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$radius" "$input" "$output" "$threads" \
                        > /dev/null 2> /dev/null
                done
            ' benchmark-loop \
            "$iterations" "$executable" "$radius" "$input" "$output" "$threads"

        elapsed="$(<"$temp_dir/calibration.time")"

        if awk -v value="$elapsed" -v target="$target_batch_seconds" \
            'BEGIN { exit !(value >= target) }'; then
            break
        fi

        if ((iterations >= max_batch_iterations)); then
            break
        fi

        iterations=$((iterations * 2))
        if ((iterations > max_batch_iterations)); then
            iterations="$max_batch_iterations"
        fi
    done

    printf "%s" "$iterations"
}

measure_configuration()
{
    local image="$1"
    local threads="$2"
    local input="$blur_dir/data/${image}.ppm"
    local reference="$reference_dir/${image}.ppm"
    local output="$temp_dir/blur_${image}_t${threads}.ppm"
    local initial_iterations
    local iterations
    local status

    if [[ ! -f "$input" ]]; then
        echo "Error: missing input file: $input" >&2
        exit 1
    fi

    if [[ ! -f "$reference" ]]; then
        echo "Error: missing reference file: $reference" >&2
        exit 1
    fi

    echo "Measuring ${image}.ppm with ${threads} thread(s)..."

    /usr/bin/time \
        -f "blur_par,${image}.ppm,${threads},%M,%e,%U,%S" \
        -a -o "$memory_raw" \
        "$blur_executable" "$radius" "$input" "$output" "$threads" \
        > /dev/null 2> /dev/null

    if cmp -s "$reference" "$output"; then
        status="PASS"
        printf "PASS: %s with %s thread(s)\n" \
            "${image}.ppm" "$threads" >> "$correctness_log"
    else
        status="FAIL"
        printf "FAIL: %s with %s thread(s) differs from %s\n" \
            "${image}.ppm" "$threads" "$reference" >> "$correctness_log"
    fi

    printf "blur_par,%s.ppm,%s,%s\n" \
        "$image" "$threads" "$status" >> "$correctness_raw"

    initial_iterations="$(initial_iterations_for_image "$image")"
    iterations="$(calibrate_iterations \
        "$initial_iterations" "$blur_executable" \
        "$input" "$output" "$threads")"

    echo "  Using ${iterations} executions per batch."

    for ((batch = 1; batch <= batches; ++batch)); do
        /usr/bin/time \
            -f "blur_par,${image}.ppm,${threads},${batch},${iterations},%e,%U,%S" \
            -a -o "$timing_raw" \
            bash -c '
                set -e
                iterations=$1
                executable=$2
                radius=$3
                input=$4
                output=$5
                threads=$6
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$radius" "$input" "$output" "$threads" \
                        > /dev/null 2> /dev/null
                done
            ' benchmark-loop \
            "$iterations" "$blur_executable" "$radius" \
            "$input" "$output" "$threads"

        sleep "$pause_seconds"
    done
}

for image in "${image_names[@]}"; do
    for threads in "${thread_counts[@]}"; do
        measure_configuration "$image" "$threads"
    done
done

awk -F, '
FILENAME == ARGV[1] {
    if (FNR == 1) next
    key = $1 SUBSEP $2 SUBSEP $3
    if (!(key in seen)) {
        seen[key] = 1
        order[++key_count] = key
        program[key] = $1
        input[key] = $2
        threads[key] = $3
    }
    batch_count[key]++
    execution_count[key] += $5
    elapsed[key] += $6
    user_time[key] += $7
    system_time[key] += $8
    sample[key, batch_count[key]] = $6 / $5
    next
}
FILENAME == ARGV[2] {
    if (FNR == 1) next
    key = $1 SUBSEP $2 SUBSEP $3
    max_rss[key] = $4
    next
}
FILENAME == ARGV[3] {
    if (FNR == 1) next
    key = $1 SUBSEP $2 SUBSEP $3
    correctness[key] = $4
    next
}
END {
    for (i = 1; i <= key_count; ++i) {
        key = order[i]
        n = batch_count[key]
        delete sorted
        for (j = 1; j <= n; ++j) sorted[j] = sample[key, j]
        for (a = 1; a <= n; ++a) {
            for (b = a + 1; b <= n; ++b) {
                if (sorted[b] < sorted[a]) {
                    temporary = sorted[a]
                    sorted[a] = sorted[b]
                    sorted[b] = temporary
                }
            }
        }
        if (n % 2) median[key] = sorted[(n + 1) / 2]
        else median[key] = (sorted[n / 2] + sorted[n / 2 + 1]) / 2

        mean[key] = elapsed[key] / execution_count[key]
        cpu[key] = (elapsed[key] > 0) \
            ? 100 * (user_time[key] + system_time[key]) / elapsed[key] \
            : 0
        mean_user[key] = user_time[key] / execution_count[key]
        mean_system[key] = system_time[key] / execution_count[key]

        if (threads[key] == 1) baseline_median[input[key]] = median[key]
    }

    print "program,input,threads,batches,executions,mean_elapsed_seconds,median_elapsed_seconds,avg_cpu_percent,avg_user_seconds,avg_system_seconds,max_rss_kb,speedup,efficiency_percent,correctness"

    for (i = 1; i <= key_count; ++i) {
        key = order[i]
        if (median[key] > 0 && baseline_median[input[key]] > 0) {
            speedup = baseline_median[input[key]] / median[key]
            efficiency = 100 * speedup / threads[key]
        } else {
            speedup = 0
            efficiency = 0
        }

        printf "%s,%s,%d,%d,%d,%.6f,%.6f,%.2f,%.6f,%.6f,%d,%.4f,%.2f,%s\n", \
            program[key], input[key], threads[key], batch_count[key], \
            execution_count[key], mean[key], median[key], cpu[key], \
            mean_user[key], mean_system[key], max_rss[key], speedup, \
            efficiency, correctness[key]
    }
}
' "$timing_raw" "$memory_raw" "$correctness_raw" > "$summary_file"

get_cxxflags()
{
    make -s -C "$blur_dir" --no-print-directory -pn \
        | awk '/^CXXFLAGS[[:space:]]*[:+?]?=/ {
            sub(/^[^=]*=[[:space:]]*/, "")
            print
            exit
        }'
}

if [[ "$run_gprof" == "1" ]]; then
    echo
    echo "Collecting representative Gprof profiles..."

    gprof_input="$blur_dir/data/${gprof_image}.ppm"
    if [[ ! -f "$gprof_input" ]]; then
        echo "Error: missing Gprof input file: $gprof_input" >&2
        exit 1
    fi

    original_flags="$(get_cxxflags)"
    instrumented_build=1
    make -C "$blur_dir" clean
    make -C "$blur_dir" CXXFLAGS="$original_flags -pg"

    for threads in "${gprof_threads[@]}"; do
        profile_dir="$temp_dir/gprof_t${threads}"
        mkdir -p "$profile_dir"
        (
            cd "$profile_dir"
            "$blur_dir/blur_par" "$radius" "$gprof_input" \
                "$temp_dir/gprof_${gprof_image}_t${threads}.ppm" \
                "$threads" \
                > /dev/null 2> "$results_dir/gprof_${gprof_image}_t${threads}.log"
            gprof "$blur_dir/blur_par" gmon.out \
                > "$results_dir/gprof_${gprof_image}_t${threads}.txt"
        )
    done

    restore_normal_build
fi

printf "program,input,threads,instruction_refs,instruction_l1_misses,instruction_ll_misses,data_refs,data_l1_misses,data_ll_misses,data_l1_miss_percent,data_ll_miss_percent,branches,branch_mispredicts,branch_mispredict_percent\n" \
    > "$callgrind_metrics"

append_callgrind_metrics()
{
    local input="$1"
    local threads="$2"
    local callgrind_file="$3"

    awk -v input="$input" -v threads="$threads" '
    /^events:/ {
        for (i = 2; i <= NF; ++i) event[i - 1] = $i
        next
    }
    /^summary:/ {
        for (i = 2; i <= NF; ++i) value[event[i - 1]] = $i
    }
    END {
        instruction_refs = value["Ir"] + 0
        instruction_l1_misses = value["I1mr"] + 0
        instruction_ll_misses = value["ILmr"] + 0
        data_refs = value["Dr"] + value["Dw"]
        data_l1_misses = value["D1mr"] + value["D1mw"]
        data_ll_misses = value["DLmr"] + value["DLmw"]
        data_l1_rate = (data_refs > 0) ? 100 * data_l1_misses / data_refs : 0
        data_ll_rate = (data_refs > 0) ? 100 * data_ll_misses / data_refs : 0
        branches = value["Bc"] + value["Bi"]
        branch_misses = value["Bcm"] + value["Bim"]
        branch_rate = (branches > 0) ? 100 * branch_misses / branches : 0

        printf "blur_par,%s.ppm,%d,%.0f,%.0f,%.0f,%.0f,%.0f,%.0f,%.4f,%.4f,%.0f,%.0f,%.4f\n", \
            input, threads, instruction_refs, instruction_l1_misses, \
            instruction_ll_misses, data_refs, data_l1_misses, \
            data_ll_misses, data_l1_rate, data_ll_rate, branches, \
            branch_misses, branch_rate
    }
    ' "$callgrind_file" >> "$callgrind_metrics"
}

if [[ "$run_callgrind" == "1" ]]; then
    echo
    echo "Collecting representative Callgrind profiles..."

    callgrind_input="$blur_dir/data/${callgrind_image}.ppm"
    if [[ ! -f "$callgrind_input" ]]; then
        echo "Error: missing Callgrind input file: $callgrind_input" >&2
        exit 1
    fi

    for threads in "${callgrind_threads[@]}"; do
        callgrind_file="$results_dir/callgrind_${callgrind_image}_t${threads}.out"
        callgrind_log="$results_dir/callgrind_${callgrind_image}_t${threads}.log"

        valgrind --tool=callgrind --cache-sim=yes --branch-sim=yes \
            --callgrind-out-file="$callgrind_file" \
            "$blur_executable" "$radius" "$callgrind_input" \
            "$temp_dir/callgrind_${callgrind_image}_t${threads}.ppm" \
            "$threads" \
            > /dev/null 2> "$callgrind_log"

        callgrind_annotate --auto=yes --threshold=95 \
            "$callgrind_file" \
            > "$results_dir/callgrind_${callgrind_image}_t${threads}.txt" \
            2> "$results_dir/callgrind_${callgrind_image}_t${threads}_annotate.log"

        append_callgrind_metrics \
            "$callgrind_image" "$threads" "$callgrind_file"
    done
fi

if [[ "$run_helgrind" == "1" ]]; then
    echo
    echo "Running Helgrind race detection..."

    helgrind_input="$blur_dir/data/${helgrind_image}.ppm"
    if [[ ! -f "$helgrind_input" ]]; then
        echo "Error: missing Helgrind input file: $helgrind_input" >&2
        exit 1
    fi

    set +e
    valgrind --tool=helgrind --error-exitcode=99 \
        --log-file="$results_dir/helgrind_${helgrind_image}_t${helgrind_threads}.txt" \
        "$blur_executable" "$radius" "$helgrind_input" \
        "$temp_dir/helgrind_${helgrind_image}_t${helgrind_threads}.ppm" \
        "$helgrind_threads" \
        > /dev/null 2> /dev/null
    helgrind_exit=$?
    set -e

    case "$helgrind_exit" in
        0) printf "PASS: Helgrind reported no errors.\n" > "$helgrind_summary" ;;
        99) printf "FAIL: Helgrind reported threading errors.\n" > "$helgrind_summary" ;;
        *) printf "ERROR: Helgrind exited with status %d.\n" \
               "$helgrind_exit" > "$helgrind_summary" ;;
    esac
fi

echo
echo "Parallel Blur summary:"
if command -v column > /dev/null 2>&1; then
    column -s, -t "$summary_file"
else
    cat "$summary_file"
fi

echo
echo "Reports written to: $results_dir"
echo "  Scalability summary: $summary_file"
echo "  Raw timing data:     $timing_raw"
echo "  Memory data:         $memory_raw"
echo "  Correctness:         $correctness_raw"
echo "  Gprof:               gprof_*.txt"
echo "  Callgrind:            callgrind_*.txt"
echo "  Cache/branch totals:  $callgrind_metrics"
echo "  Helgrind:             $helgrind_summary"

echo
echo "Cleaning parallel Blur build files..."
make -C "$blur_dir" clean
