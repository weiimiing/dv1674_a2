#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

usage()
{
    cat <<'EOF'
Usage: ./profile_parallel.sh pearson|blur|both

Examples:
  MAX_THREADS=8 ./profile_parallel.sh pearson
  MAX_THREADS=8 ./profile_parallel.sh blur
  THREAD_COUNTS="1 2 4 6 8" ./profile_parallel.sh both

Common optional settings:
  THREAD_COUNTS             Exact thread counts to test.
  MAX_THREADS               Generate powers of two up to this limit.
  BATCHES                   Measurement batches per configuration (default: 5).
  PAUSE_SECONDS             Pause between batches (default: 1).
  RUN_GPROF                 Set to 0 to skip Gprof.
  RUN_CALLGRIND             Set to 0 to skip Callgrind.
  RUN_HELGRIND              Set to 0 to skip Helgrind.

Blur-specific settings:
  IMAGES                    Image names without .ppm (default: im1 im2 im3 im4).
  BLUR_RADIUS               Blur radius (default: 15).
  GPROF_IMAGE               Gprof image (default: im4).
  CALLGRIND_IMAGE           Callgrind image (default: im2).
  HELGRIND_IMAGE            Helgrind image (default: im1).
  BLUR_RESULTS_DIR          Override the Blur results directory.

Pearson-specific settings:
  DATASET_SIZES             Dataset sizes (default: 128 256 512 1024).
  GPROF_SIZE                Gprof dataset size (default: 1024).
  CALLGRIND_SIZE            Callgrind dataset size (default: 512).
  HELGRIND_SIZE             Helgrind dataset size (default: 128).
  PEARSON_RESULTS_DIR       Override the Pearson results directory.
EOF
}

if (($# != 1)); then
    usage >&2
    exit 2
fi

case "$1" in
    pearson)
        exec "$repo_root/profile_parallel_pearson.sh"
        ;;
    blur)
        exec "$repo_root/profile_parallel_blur.sh"
        ;;
    both)
        if [[ -n "${RESULTS_DIR:-}" ]]; then
            echo "Error: RESULTS_DIR is ambiguous when running both programs." >&2
            echo "Use PEARSON_RESULTS_DIR and BLUR_RESULTS_DIR instead." >&2
            exit 2
        fi
        "$repo_root/profile_parallel_pearson.sh"
        "$repo_root/profile_parallel_blur.sh"
        ;;
    -h|--help)
        usage
        ;;
    *)
        echo "Error: choose pearson, blur, or both." >&2
        usage >&2
        exit 2
        ;;
esac
