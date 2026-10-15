#!/bin/bash
# Usage: ./compare_stages.sh <A_bin> <A_label> <B_bin> <B_label> [radius] [runs]

A_BIN=$(realpath "${1:?}"); A_LABEL="${2:?}"
B_BIN=$(realpath "${3:?}"); B_LABEL="${4:?}"
RADIUS=${5:-15}
RUNS=${6:-5}
DATA_DIR=$(dirname "$A_BIN")/data

median() { printf '%s\n' "$@" | sort -n | awk '{a[NR]=$1} END{print a[int((NR+1)/2)]}'; }

run_one() {
    local bin="$1" img="$2"
    local walls=()
    for i in $(seq 1 "$RUNS"); do
        local out
        out=$(/usr/bin/time -f "%e" "$bin" "$RADIUS" "$img" /tmp/compare_out.ppm 2>&1 >/dev/null)
        walls+=("$out")
    done
    median "${walls[@]}"
}

echo "$A_LABEL vs $B_LABEL   (radius=$RADIUS, runs=$RUNS, median wall time)"
echo "--------------------------------------------------------"
printf "%-10s %10s %10s %10s\n" "image" "$A_LABEL" "$B_LABEL" "speedup"
echo "--------------------------------------------------------"

for img in "$DATA_DIR"/*.ppm; do
    name=$(basename "$img")
    a=$(run_one "$A_BIN" "$img")
    b=$(run_one "$B_BIN" "$img")
    sp=$(awk -v a="$a" -v b="$b" 'BEGIN { printf "%.2fx", a/b }')
    printf "%-10s %10s %10s %10s\n" "$name" "$a" "$b" "$sp"
done
