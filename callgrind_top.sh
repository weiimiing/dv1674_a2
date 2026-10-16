#!/bin/bash
FILE=${1:?usage: $0 <callgrind.txt> [N]}
N=${2:-10}

awk -v n="$N" '
    # start collecting only when we hit the "file:function" header
    /file:function/ { in_funcs = 1; next }
    # stop when we hit the auto-annotated section
    /Auto-annotated/ { exit }
    # skip separator lines
    /^----/ { next }
    # only data rows: start with a number that has a percent in parentheses
    in_funcs && /^[0-9,]+ / {
        # Ir is field 1, percent is field 2
        ir = $1
        pct = $2
        # function name is last field
        fn = $NF
        # drop leading path
        sub(/.*[\/:]/, "", fn)
        # drop trailing "[...]" annotation
        sub(/\[.*$/, "", fn)
        printf "%-55s %18s %12s\n", fn, ir, pct
        count++
        if (count >= n) exit
    }
' "$FILE"
