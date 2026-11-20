#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
. "$SCRIPT_DIR/full-game-benchmarks.sh"

PROFILE_ROOT="$PROJECT_ROOT/backend/profiles"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
BENCH_COUNT="${BENCH_COUNT:-10}"
SELECTED="${BENCH:-}"
PGO_FLAG="$(shipped_pgo_flag "$PROJECT_ROOT")"

if [[ -n $SELECTED ]] && ! benchmark_known "$SELECTED"; then
    echo "unknown benchmark BENCH=$SELECTED, expected one of: ${!FULL_GAME_BENCHMARKS[*]}"
    exit 1
fi

for name in "${FULL_GAME_BENCHMARK_ORDER[@]}"; do
    if [[ -n $SELECTED && $name != "$SELECTED" ]]; then
        continue
    fi

    read -r package benchmark <<< "${FULL_GAME_BENCHMARKS[$name]}"
    dir="$PROFILE_ROOT/${name}_$STAMP"
    mkdir -p "$dir"
    echo "=== $name: $benchmark ($package), $BENCH_COUNT runs, $PGO_FLAG ==="
    go test -C "$PROJECT_ROOT/backend/game_v2" -run '^$' -bench "^$benchmark\$" -benchmem -count "$BENCH_COUNT" \
        "$PGO_FLAG" -cpuprofile "$dir/cpu.prof" -memprofile "$dir/allocs.prof" -o "$dir/bench.test" "$package" |
        tee "$dir/bench.txt"
    echo ""
    (cd "$PROJECT_ROOT/backend/game_v2" && go tool benchstat "$name=$dir/bench.txt")
    echo ""
    bash "$SCRIPT_DIR/profile-report.sh" "$dir"
    echo ""
done
