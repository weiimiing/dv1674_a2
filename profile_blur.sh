#!/usr/bin/env bash
#
# profile_blur.sh
#
# Blur-only profiling harness. Collects, for a single stage:
#   - timing (multiple batches, calibrated iterations, median)
#   - memory (max RSS via /usr/bin/time)
#   - correctness (byte-compare vs. a reference output)
#   - gprof function profile (on im4)
#   - callgrind cache/branch stats (on im2)
#
# Results go to:
#   results/blur/<stage>/
#
# Usage:
#   ./profile_blur.sh <stage_name> <stage_path>
#
# Example:
#   ./profile_blur.sh baseline_original versions/baseline_original
#   ./profile_blur.sh opt1              versions/optimizations_1
#
# All numbers are written to CSV files under results/blur/<stage>/,
# ready to plot with any tool.

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stage_name="${1:?usage: $0 <stage_name> <stage_path>}"
stage_path="${2:?usage: $0 <stage_name> <stage_path>}"

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
blur_dir="$stage_dir/blur"
results_dir="$repo_root/results/blur/$stage_name"
temp_dir="$(mktemp -d /tmp/blur-profile.XXXXXX)"

# Tunables (override via environment)
batches="${BATCHES:-5}"
pause_seconds="${PAUSE_SECONDS:-1}"
target_batch_seconds="${TARGET_BATCH_SECONDS:-2}"
max_batch_iterations="${MAX_BATCH_ITERATIONS:-100000}"
radius="${RADIUS:-15}"
run_gprof="${RUN_GPROF:-1}"
run_callgrind="${RUN_CALLGRIND:-1}"
blur_gprof_image="${BLUR_GPROF_IMAGE:-im4}"
blur_callgrind_image="${BLUR_CALLGRIND_IMAGE:-im2}"

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
    echo "Restoring normal build for stage '$stage_name'..."
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

# Check required tools
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

if [[ ! -d "$blur_dir" ]]; then
    echo "Error: blur directory not found: $blur_dir" >&2
    exit 1
fi
if [[ ! -x "$blur_dir/blur" && ! -f "$blur_dir/blur.cpp" ]]; then
    echo "Error: no blur binary or source found in $blur_dir" >&2
    exit 1
fi

mkdir -p "$results_dir"
: > "$correctness_log"
printf "program,input,batch,iterations,total_elapsed_seconds,user_seconds,system_seconds\n" > "$timing_raw"
printf "program,input,max_rss_kb,direct_elapsed_seconds,user_seconds,system_seconds\n" > "$memory_raw"
printf "program,input,status\n" > "$correctness_raw"

echo "Building normal executables for stage '$stage_name'..."
restore_normal_builds

# Reference outputs: use the pristine baseline binaries to generate them.
# If the baseline lives at versions/baseline_original, that's the source of truth.
reference_dir="$repo_root/results/reference/blur"
mkdir -p "$reference_dir"

generate_reference()
{
    local image="$1"
    local ref="$reference_dir/${image}.ppm"
    if [[ -f "$ref" ]]; then
        return 0
    fi
    local baseline_blur="$repo_root/versions/baseline/blur/blur"
    if [[ ! -x "$baseline_blur" ]]; then
        echo "Error: baseline blur binary not found at $baseline_blur" >&2
        echo "Cannot generate reference outputs for correctness checking." >&2
        exit 1
    fi
    echo "Generating reference for ${image}.ppm from baseline..."
    "$baseline_blur" "$radius" "$blur_dir/data/${image}.ppm" "$ref"
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
                radius=$3
                input=$4
                output=$5
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$radius" "$input" "$output"
                done
            ' benchmark-loop "$iterations" "$blur_dir/blur" "$radius" "$input" "$output"
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

measure_blur()
{
    local image="$1"
    local initial_iterations="$2"
    local input="$blur_dir/data/${image}.ppm"
    local reference="$reference_dir/${image}.ppm"
    local output="$temp_dir/blur_${image}.ppm"
    local status

    if [[ ! -f "$input" ]]; then
        echo "Error: missing input image $input" >&2
        exit 1
    fi

    generate_reference "$image"

    echo "Measuring Blur ${image}.ppm..."
    /usr/bin/time \
        -f "blur,${image}.ppm,%M,%e,%U,%S" \
        -a -o "$memory_raw" \
        "$blur_dir/blur" "$radius" "$input" "$output"

    if cmp -s "$reference" "$output"; then
        status="PASS"
    else
        status="FAIL"
        echo "Blur ${image}.ppm differs from reference." >> "$correctness_log"
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
                radius=$3
                input=$4
                output=$5
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$radius" "$input" "$output"
                done
            ' benchmark-loop "$calibrated_iterations" "$blur_dir/blur" "$radius" "$input" "$output"
        sleep "$pause_seconds"
    done
}

# Initial iteration seeds per image (small images get more iterations per batch).
measure_blur im1 10
measure_blur im2 5
measure_blur im3 3
measure_blur im4 1

# Aggregate timing/memory/correctness into a single summary.csv
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
    blur_original_flags="$(get_cxxflags "$blur_dir")"

    echo
    echo "Building gprof-instrumented executable..."
    restore_needed=1
    make -C "$blur_dir" clean
    make -C "$blur_dir" CXXFLAGS="$blur_original_flags -g -pg"

    mkdir -p "$temp_dir/gprof_blur"
    (
        cd "$temp_dir/gprof_blur"
        "$blur_dir/blur" "$radius" \
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
    echo "Running Callgrind with cache and branch simulation on ${blur_callgrind_image}.ppm..."
    valgrind --tool=callgrind --cache-sim=yes --branch-sim=yes \
        --callgrind-out-file="$results_dir/blur_callgrind.out" \
        "$blur_dir/blur" "$radius" \
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
echo "  Summary:      $summary_file"
echo "  gprof:        $results_dir/blur_gprof.txt"
echo "  Callgrind:    $results_dir/blur_callgrind.txt"
echo "  Cache/branch: $profile_metrics"
