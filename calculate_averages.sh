#!/usr/bin/env bash
set -euo pipefail

input="results/baseline/summary.csv"
output="results/baseline/averages.csv"

if [[ ! -f "$input" ]]; then
    echo "Error: $input does not exist. Run baseline_benchmark first."
    exit 1
fi

awk -F, '
NR > 1 {
    gsub(/%/, "", $5)
    key = $1 "," $2
    elapsed[key] += $4
    cpu[key] += $5
    memory[key] += $6
    runs[key]++
}
END {
    print "program,input,avg_elapsed_seconds,avg_cpu_percent,avg_max_rss_kb"
    for (key in runs) {
        printf "%s,%.4f,%.2f,%.0f\n",
            key,
            elapsed[key] / runs[key],
            cpu[key] / runs[key],
            memory[key] / runs[key]
    }
}' "$input" > "$output"

echo "Averages:"
column -s, -t "$output"