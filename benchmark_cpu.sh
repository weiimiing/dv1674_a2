#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

batches="${BATCHES:-5}"
pause_seconds="${PAUSE_SECONDS:-1}"
results_dir="results/baseline"
raw_file="$results_dir/cpu_raw.csv"
batch_file="$results_dir/cpu_batches.csv"
average_file="$results_dir/cpu_averages.csv"

pearson_dir="versions/baseline/pearson"
blur_dir="versions/baseline/blur"

mkdir -p "$results_dir"

if [[ ! -x "$pearson_dir/pearson" ]]; then
    make -C "$pearson_dir"
fi

if [[ ! -x "$blur_dir/blur" ]]; then
    make -C "$blur_dir"
fi

printf "program,input,batch,iterations,total_elapsed_seconds,user_seconds,system_seconds\n" > "$raw_file"

benchmark_pearson()
{
    local size="$1"
    local iterations="$2"
    local input="$pearson_dir/data/${size}.data"
    local output="/tmp/a2_cpu_pearson_${size}.data"

    # Warm up file and instruction caches before collecting samples.
    "$pearson_dir/pearson" "$input" "$output"

    for ((batch = 1; batch <= batches; ++batch)); do
        echo "Pearson ${size}.data: batch ${batch}/${batches} (${iterations} executions)"
        /usr/bin/time \
            -f "pearson,${size}.data,${batch},${iterations},%e,%U,%S" \
            -a -o "$raw_file" \
            bash -c '
                iterations=$1
                executable=$2
                input=$3
                output=$4
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" "$input" "$output"
                done
            ' benchmark-loop "$iterations" "$pearson_dir/pearson" "$input" "$output"
        sleep "$pause_seconds"
    done
}

benchmark_blur()
{
    local image="$1"
    local iterations="$2"
    local input="$blur_dir/data/${image}.ppm"
    local output="/tmp/a2_cpu_blur_${image}.ppm"

    "$blur_dir/blur" 15 "$input" "$output"

    for ((batch = 1; batch <= batches; ++batch)); do
        echo "Blur ${image}.ppm: batch ${batch}/${batches} (${iterations} executions)"
        /usr/bin/time \
            -f "blur,${image}.ppm,${batch},${iterations},%e,%U,%S" \
            -a -o "$raw_file" \
            bash -c '
                iterations=$1
                executable=$2
                input=$3
                output=$4
                for ((i = 0; i < iterations; ++i)); do
                    "$executable" 15 "$input" "$output"
                done
            ' benchmark-loop "$iterations" "$blur_dir/blur" "$input" "$output"
        sleep "$pause_seconds"
    done
}

# Each batch lasts several seconds so CPU accounting has enough resolution.
benchmark_pearson 128 100
benchmark_pearson 256 20
benchmark_pearson 512 3
benchmark_pearson 1024 1

benchmark_blur im1 10
benchmark_blur im2 5
benchmark_blur im3 3
benchmark_blur im4 1

awk -F, '
BEGIN {
    OFS = ","
    print "program,input,batch,iterations,total_elapsed_seconds,avg_elapsed_seconds,cpu_percent"
}
NR > 1 {
    average_elapsed = $5 / $4
    cpu_percent = ($5 > 0) ? 100 * ($6 + $7) / $5 : 0
    printf "%s,%s,%d,%d,%.6f,%.6f,%.2f\n", $1, $2, $3, $4, $5, average_elapsed, cpu_percent
}
' "$raw_file" > "$batch_file"

awk -F, '
BEGIN {
    OFS = ","
    print "program,input,batches,executions,avg_elapsed_seconds,avg_cpu_percent,total_elapsed_seconds,total_cpu_seconds"
}
NR > 1 {
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
    cpu_time[key] += $6 + $7
}
END {
    for (i = 1; i <= key_count; ++i) {
        key = order[i]
        average_elapsed = elapsed[key] / execution_count[key]
        average_cpu = (elapsed[key] > 0) ? 100 * cpu_time[key] / elapsed[key] : 0
        printf "%s,%s,%d,%d,%.6f,%.2f,%.6f,%.6f\n", \
            program[key], input[key], batch_count[key], execution_count[key], \
            average_elapsed, average_cpu, elapsed[key], cpu_time[key]
    }
}
' "$raw_file" > "$average_file"

echo
echo "Weighted CPU-utilization averages:"
if command -v column > /dev/null 2>&1; then
    column -s, -t "$average_file"
else
    cat "$average_file"
fi

echo
echo "Raw measurements: $raw_file"
echo "Per-batch metrics: $batch_file"
echo "Final averages: $average_file"
