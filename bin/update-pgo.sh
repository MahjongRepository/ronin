#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
. "$SCRIPT_DIR/full-game-benchmarks.sh"

MODULE_DIR="$PROJECT_ROOT/backend/game_v2"
PGO_FILE="$MODULE_DIR/cmd/gameserver/default.pgo"
BENCH_COUNT="${BENCH_COUNT:-5}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

profiles=()
for extra in "$@"; do
    if [[ ! -s $extra ]]; then
        echo "no CPU profile at $extra"
        exit 1
    fi
    profiles+=("$(cd "$(dirname "$extra")" && pwd)/$(basename "$extra")")
done

for name in "${FULL_GAME_BENCHMARK_ORDER[@]}"; do
    read -r package benchmark <<< "${FULL_GAME_BENCHMARKS[$name]}"
    echo "profiling $name: $benchmark ($package), $BENCH_COUNT runs without PGO..."
    go test -C "$MODULE_DIR" -run '^$' -bench "^$benchmark\$" -count "$BENCH_COUNT" -pgo=off \
        -cpuprofile "$WORK_DIR/$name.prof" -o "$WORK_DIR/$name.test" "$package" > /dev/null
    profiles+=("$WORK_DIR/$name.prof")
done

go tool pprof -proto "${profiles[@]}" > "$WORK_DIR/default.pgo"
mv "$WORK_DIR/default.pgo" "$PGO_FILE"
echo "wrote $PGO_FILE from ${#profiles[@]} profile(s)"
