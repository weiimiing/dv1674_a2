#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stage_name="${1:-baseline}"
stage_path="${2:-versions/baseline}"

if [[ ! "$stage_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Error: stage name may only contain letters, numbers, dots, underscores, and hyphens." >&2
    exit 1
fi

if [[ "$stage_path" != /* ]]; then
    stage_path="$repo_root/$stage_path"
fi
if [[ ! -d "$stage_path" ]]; then
    echo "Error: stage directory does not exist: $stage_path" >&2
    exit 1
fi

stage_dir="$(cd -- "$stage_path" && pwd)"
pearson_dir="$stage_dir/pearson"
blur_dir="$stage_dir/blur"
reference_dir="$repo_root/results/reference"
results_dir="$repo_root/results/profiling/$stage_name"
temp_dir="$(mktemp -d /tmp/a2-stage-profile.XXXXXX)"

batches="${BATCHES:-5}"
pause_seconds="${PAUSE_SECONDS:-1}"
target_batch_seconds="${TARGET_BATCH_SECONDS:-2}"
max_batch_iterations="${MAX_BATCH_ITERATIONS:-100000}"
run_gprof="${RUN_GPROF:-1}"
run_callgrind="${RUN_CALLGRIND:-1}"

pearson_gprof_size="${PEARSON_GPROF_SIZE:-1024}"
blur_gprof_image="${BLUR_GPROF_IMAGE:-im4}"
pearson_callgrind_size="${PEARSON_CALLGRIND_SIZE:-256}"
blur_callgrind_image="${BLUR_CALLGRIND_IMAGE:-im1}"

timing_raw="$results_dir/timing_raw.csv"
memory_raw="$results_dir/memory_raw.csv"
correctness_raw="$results_dir/correctness.csv"
summary_file="$results_dir/summary.csv"
profile_metrics="$results_dir/callgrind_metrics.csv"
correctness_log="$results_dir/correctness_details.txt"
restore_needed=0
calibrated_iterations=1

restore_normal_builds()
{
    echo "Restoring normal builds for stage '$stage_name'..."
    make -C "$pearson_dir" clean
    make -C "$pearson_dir"
    make -C "$blur_dir" clean
    make -C "$blur_dir"
}

cleanup()
{
    local status=$?
    trap - EXIT
    rm -rf -- "$temp_dir"

    if ((restore_needed)); then
        set +e
        restore_normal_builds
        local restore_status=$?
        set -e
        if ((status == 0 && restore_status != 0)); then
            status=$restore_status
        fi
    fi

    exit "$status"
}

trap cleanup EXIT

for required_command in make gprof valgrind callgrind_annotate awk cmp; do
    if ! command -v "$required_command" > /dev/null 2>&1; then
        echo "Error: required command '$required_command' is not installed." >&2
        exit 1
    fi
done
if [[ ! -x /usr/bin/time ]]; then
    echo "Error: GNU time was not found at /usr/bin/time." >&2
    exit 1
fi

for required_dir in "$pearson_dir" "$blur_dir"; do
    if [[ ! -d "$required_dir" ]]; then
        echo "Error: expected application directory does not exist: $required_dir" >&2
        exit 1
    fi
done

mkdir -p "$results_dir"
: > "$correctness_log"
printf "program,input,batch,iterations,total_elapsed_seconds,user_seconds,system_seconds\n" > "$timing_raw"
printf "program,input,max_rss_kb,direct_elapsed_seconds,user_seconds,system_seconds\n" > "$memory_raw"
printf "program,input,status\n" > "$correctness_raw"

echo "Building normal executables for stage '$stage_name'..."
restore_normal_builds

calibrate_pearson()
{
    local initial_iterations="$1"
    local input="$2"
    local output="$3"
    local iterations="$initial_iterations"
    local elapsed

    while true; do
        /usr/bin/time -f "%e" -o "$temp_dir/calibration.time" \
            bash -c '
                iterations=$1
                executable=$2
                input=$3
                output=$4
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$input" "$output"
                done
            ' benchmark-loop "$iterations" "$pearson_dir/pearson" "$input" "$output"
        elapsed="$(<"$temp_dir/calibration.time")"

        if awk -v value="$elapsed" -v target="$target_batch_seconds" \
            'BEGIN { exit !(value >= target) }'; then
            break
        fi
        if ((iterations >= max_batch_iterations)); then
            break
        fi
        iterations=$((iterations * 2))
    done

    calibrated_iterations="$iterations"
}

calibrate_blur()
{
    local initial_iterations="$1"
    local input="$2"
    local output="$3"
    local iterations="$initial_iterations"
    local elapsed

    while true; do
        /usr/bin/time -f "%e" -o "$temp_dir/calibration.time" \
            bash -c '
                iterations=$1
                executable=$2
                input=$3
                output=$4
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" 15 "$input" "$output"
                done
            ' benchmark-loop "$iterations" "$blur_dir/blur" "$input" "$output"
        elapsed="$(<"$temp_dir/calibration.time")"

        if awk -v value="$elapsed" -v target="$target_batch_seconds" \
            'BEGIN { exit !(value >= target) }'; then
            break
        fi
        if ((iterations >= max_batch_iterations)); then
            break
        fi
        iterations=$((iterations * 2))
    done

    calibrated_iterations="$iterations"
}

measure_pearson()
{
    local size="$1"
    local initial_iterations="$2"
    local input="$pearson_dir/data/${size}.data"
    local reference="$reference_dir/pearson/${size}.data"
    local output="$temp_dir/pearson_${size}.data"
    local status

    if [[ ! -f "$input" || ! -f "$reference" ]]; then
        echo "Error: missing Pearson input or reference for ${size}.data." >&2
        exit 1
    fi

    echo "Measuring Pearson ${size}.data..."
    /usr/bin/time \
        -f "pearson,${size}.data,%M,%e,%U,%S" \
        -a -o "$memory_raw" \
        "$pearson_dir/pearson" "$input" "$output"

    if "$pearson_dir/verify" "$reference" "$output" \
        >> "$correctness_log" 2>&1; then
        status="PASS"
    else
        case $? in
            1) status="WARNING" ;;
            *) status="FAIL" ;;
        esac
    fi
    printf "pearson,%s.data,%s\n" "$size" "$status" >> "$correctness_raw"

    calibrate_pearson "$initial_iterations" "$input" "$output"
    echo "  Using ${calibrated_iterations} executions per batch."
    for ((batch = 1; batch <= batches; ++batch)); do
        /usr/bin/time \
            -f "pearson,${size}.data,${batch},${calibrated_iterations},%e,%U,%S" \
            -a -o "$timing_raw" \
            bash -c '
                iterations=$1
                executable=$2
                input=$3
                output=$4
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$input" "$output"
                done
            ' benchmark-loop "$calibrated_iterations" "$pearson_dir/pearson" "$input" "$output"
        sleep "$pause_seconds"
    done
}

measure_blur()
{
    local image="$1"
    local initial_iterations="$2"
    local input="$blur_dir/data/${image}.ppm"
    local reference="$reference_dir/blur/${image}.ppm"
    local output="$temp_dir/blur_${image}.ppm"
    local status

    if [[ ! -f "$input" || ! -f "$reference" ]]; then
        echo "Error: missing Blur input or reference for ${image}.ppm." >&2
        exit 1
    fi

    echo "Measuring Blur ${image}.ppm..."
    /usr/bin/time \
        -f "blur,${image}.ppm,%M,%e,%U,%S" \
        -a -o "$memory_raw" \
        "$blur_dir/blur" 15 "$input" "$output"

    if cmp -s "$reference" "$output"; then
        status="PASS"
    else
        status="FAIL"
        echo "Blur ${image}.ppm differs from its reference." >> "$correctness_log"
    fi
    printf "blur,%s.ppm,%s\n" "$image" "$status" >> "$correctness_raw"

    calibrate_blur "$initial_iterations" "$input" "$output"
    echo "  Using ${calibrated_iterations} executions per batch."
    for ((batch = 1; batch <= batches; ++batch)); do
        /usr/bin/time \
            -f "blur,${image}.ppm,${batch},${calibrated_iterations},%e,%U,%S" \
            -a -o "$timing_raw" \
            bash -c '
                iterations=$1
                executable=$2
                input=$3
                output=$4
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" 15 "$input" "$output"
                done
            ' benchmark-loop "$calibrated_iterations" "$blur_dir/blur" "$input" "$output"
        sleep "$pause_seconds"
    done
}

measure_pearson 128 100
measure_pearson 256 20
measure_pearson 512 3
measure_pearson 1024 1

measure_blur im1 10
measure_blur im2 5
measure_blur im3 3
measure_blur im4 1

awk -F, -v stage="$stage_name" '
FILENAME == ARGV[1] {
    if (FNR == 1) next
    key = $1 SUBSEP $2
    if (!(key in seen)) {
        seen[key] = 1
        order[++key_count] = key
        program[key] = $1
        input[key] = $2
    }
    batch_count[key]++
    execution_count[key] += $4
    elapsed[key] += $5
    user_time[key] += $6
    system_time[key] += $7
    sample[key, batch_count[key]] = $5 / $4
    next
}
FILENAME == ARGV[2] {
    if (FNR == 1) next
    key = $1 SUBSEP $2
    max_rss[key] = $3
    next
}
FILENAME == ARGV[3] {
    if (FNR == 1) next
    key = $1 SUBSEP $2
    correctness[key] = $3
    next
}
END {
    print "stage,program,input,batches,executions,mean_elapsed_seconds,median_elapsed_seconds,avg_cpu_percent,avg_user_seconds,avg_system_seconds,max_rss_kb,correctness"
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
        if (n % 2) median = sorted[(n + 1) / 2]
        else median = (sorted[n / 2] + sorted[n / 2 + 1]) / 2

        mean = elapsed[key] / execution_count[key]
        cpu = (elapsed[key] > 0) ? 100 * (user_time[key] + system_time[key]) / elapsed[key] : 0
        mean_user = user_time[key] / execution_count[key]
        mean_system = system_time[key] / execution_count[key]

        printf "%s,%s,%s,%d,%d,%.6f,%.6f,%.2f,%.6f,%.6f,%d,%s\n", \
            stage, program[key], input[key], n, execution_count[key], mean, median, cpu, \
            mean_user, mean_system, max_rss[key], correctness[key]
    }
}
' "$timing_raw" "$memory_raw" "$correctness_raw" > "$summary_file"

get_cxxflags()
{
    make -s -C "$1" --no-print-directory -pn \
        | awk '/^CXXFLAGS[[:space:]]*[:+?]?=/ { sub(/^[^=]*=[[:space:]]*/, ""); print; exit }'
}

if [[ "$run_gprof" == "1" ]]; then
    pearson_original_flags="$(get_cxxflags "$pearson_dir")"
    blur_original_flags="$(get_cxxflags "$blur_dir")"

    echo
    echo "Building gprof-instrumented executables..."
    restore_needed=1
    make -C "$pearson_dir" clean
    make -C "$pearson_dir" CXXFLAGS="$pearson_original_flags -g -pg"
    make -C "$blur_dir" clean
    make -C "$blur_dir" CXXFLAGS="$blur_original_flags -g -pg"

    mkdir -p "$temp_dir/gprof_pearson" "$temp_dir/gprof_blur"
    (
        cd "$temp_dir/gprof_pearson"
        "$pearson_dir/pearson" \
            "$pearson_dir/data/${pearson_gprof_size}.data" \
            "$temp_dir/pearson_gprof_output.data"
        gprof "$pearson_dir/pearson" gmon.out > "$results_dir/pearson_gprof.txt"
    )
    (
        cd "$temp_dir/gprof_blur"
        "$blur_dir/blur" 15 \
            "$blur_dir/data/${blur_gprof_image}.ppm" \
            "$temp_dir/blur_gprof_output.ppm"
        gprof "$blur_dir/blur" gmon.out > "$results_dir/blur_gprof.txt"
    )

    restore_normal_builds
    restore_needed=0
fi

printf "stage,program,input,instruction_refs,instruction_l1_misses,instruction_ll_misses,data_refs,data_l1_misses,data_ll_misses,data_l1_miss_percent,data_ll_miss_percent,branches,branch_mispredicts,branch_mispredict_percent\n" > "$profile_metrics"

append_callgrind_metrics()
{
    local program="$1"
    local input="$2"
    local callgrind_file="$3"

    awk -v stage="$stage_name" -v program="$program" -v input="$input" '
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
        data_reads = value["Dr"] + 0
        data_writes = value["Dw"] + 0
        data_refs = data_reads + data_writes
        data_l1_misses = value["D1mr"] + value["D1mw"]
        data_ll_misses = value["DLmr"] + value["DLmw"]
        data_l1_rate = (data_refs > 0) ? 100 * data_l1_misses / data_refs : 0
        data_ll_rate = (data_refs > 0) ? 100 * data_ll_misses / data_refs : 0
        branches = value["Bc"] + value["Bi"]
        branch_misses = value["Bcm"] + value["Bim"]
        branch_rate = (branches > 0) ? 100 * branch_misses / branches : 0

        printf "%s,%s,%s,%.0f,%.0f,%.0f,%.0f,%.0f,%.0f,%.4f,%.4f,%.0f,%.0f,%.4f\n", \
            stage, program, input, instruction_refs, instruction_l1_misses, \
            instruction_ll_misses, data_refs, data_l1_misses, data_ll_misses, \
            data_l1_rate, data_ll_rate, branches, branch_misses, branch_rate
    }
    ' "$callgrind_file" >> "$profile_metrics"
}

if [[ "$run_callgrind" == "1" ]]; then
    echo
    echo "Running Callgrind with cache and branch simulation..."
    valgrind --tool=callgrind --cache-sim=yes --branch-sim=yes \
        --callgrind-out-file="$results_dir/pearson_callgrind.out" \
        "$pearson_dir/pearson" \
        "$pearson_dir/data/${pearson_callgrind_size}.data" \
        "$temp_dir/pearson_callgrind_output.data" \
        2> "$results_dir/pearson_callgrind_log.txt"

    callgrind_annotate --auto=yes --threshold=95 \
        "$results_dir/pearson_callgrind.out" \
        > "$results_dir/pearson_callgrind.txt"
    append_callgrind_metrics \
        "pearson" "${pearson_callgrind_size}.data" \
        "$results_dir/pearson_callgrind.out"

    valgrind --tool=callgrind --cache-sim=yes --branch-sim=yes \
        --callgrind-out-file="$results_dir/blur_callgrind.out" \
        "$blur_dir/blur" 15 \
        "$blur_dir/data/${blur_callgrind_image}.ppm" \
        "$temp_dir/blur_callgrind_output.ppm" \
        2> "$results_dir/blur_callgrind_log.txt"

    callgrind_annotate --auto=yes --threshold=95 \
        "$results_dir/blur_callgrind.out" \
        > "$results_dir/blur_callgrind.txt"
    append_callgrind_metrics \
        "blur" "${blur_callgrind_image}.ppm" \
        "$results_dir/blur_callgrind.out"
fi

echo
echo "Stage summary:"
if command -v column > /dev/null 2>&1; then
    column -s, -t "$summary_file"
else
    cat "$summary_file"
fi

echo
echo "Reports written to: $results_dir"
echo "  Main metrics: $summary_file"
echo "  gprof reports: *_gprof.txt"
echo "  Callgrind reports: *_callgrind.txt"
echo "  Cache/branch totals: $profile_metrics"
