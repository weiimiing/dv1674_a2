#!/bin/bash
# bench.sh
# Usage: ./bench.sh <binary> [radius] [runs]
# Runs every image in data/ and reports median wall, user, sys time and max RSS.

BIN=$(realpath "${1:?usage: $0 <binary> [radius] [runs]}")
RADIUS=${2:-15}
RUNS=${3:-5}
DIR=$(dirname "$BIN")

echo "binary = $BIN"
echo "radius = $RADIUS    runs = $RUNS    (median shown)"
echo "----------------------------------------------------------------------------"
printf "%-10s %10s %10s %10s %12s\n" "image" "wall(s)" "user(s)" "sys(s)" "maxRSS(MB)"
echo "----------------------------------------------------------------------------"

cd "$DIR" || exit 1

for img in data/*.ppm; do
    name=$(basename "$img")
    walls=(); users=(); syss=(); rss_max=0

    for i in $(seq 1 "$RUNS"); do
        out=$(/usr/bin/time -f "%e %U %S %M" "$BIN" "$RADIUS" "$img" /tmp/bench_out.ppm 2>&1 >/dev/null)
        w=$(echo "$out" | awk '{print $1}')
        u=$(echo "$out" | awk '{print $2}')
        s=$(echo "$out" | awk '{print $3}')
        m=$(echo "$out" | awk '{print $4}')
        walls+=("$w"); users+=("$u"); syss+=("$s")
        [ "$m" -gt "$rss_max" ] && rss_max=$m
    done

    median() { printf '%s\n' "$@" | sort -n | awk '{a[NR]=$1} END{print a[int((NR+1)/2)]}'; }
    mw=$(median "${walls[@]}")
    mu=$(median "${users[@]}")
    ms=$(median "${syss[@]}")
    mrss=$(( rss_max / 1024 ))

    printf "%-10s %10s %10s %10s %12s\n" "$name" "$mw" "$mu" "$ms" "$mrss"
done
