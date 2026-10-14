#!/bin/bash
# verify_seq.sh — compares two blur binaries byte-for-byte.
# Usage: ./verify_seq.sh <baseline_blur> <test_blur>

BASE=${1:?usage: $0 <baseline_blur> <test_blur>}
TEST=${2:?usage: $0 <baseline_blur> <test_blur>}
RADIUS=15

SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT

cd "$(dirname "$(realpath "$TEST")")" || exit 1

printf "%-10s %-14s %-10s\n" "image" "size" "result"
printf "%-10s %-14s %-10s\n" "------" "------" "------"

fail=0
for img in data/*.ppm; do
    name=$(basename "$img" .ppm)
    size=$(awk 'NR>1 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ {print $1" x "$2; exit}' "$img")

    "$BASE" $RADIUS "$img" "$SCRATCH/${name}_base.ppm" 2>/dev/null
    "$TEST" $RADIUS "$img" "$SCRATCH/${name}_test.ppm" 2>/dev/null

    if cmp -s "$SCRATCH/${name}_base.ppm" "$SCRATCH/${name}_test.ppm"; then
        printf "%-10s %-14s %-10s\n" "$name" "$size" "IDENTICAL"
    else
        printf "%-10s %-14s %-10s\n" "$name" "$size" "DIFFERENT"
        fail=1
    fi
done

echo
if [ $fail -eq 0 ]; then
    echo "All outputs match."
else
    echo "One or more outputs differ."
fi
exit $fail
