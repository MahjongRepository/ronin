#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
. "$SCRIPT_DIR/full-game-benchmarks.sh"

if [[ $# -ne 1 || ! -d $1/backend/game_v2 ]]; then
    echo "usage: $0 <baseline checkout of this repo, such as a git worktree of the base commit>"
    exit 2
fi

BASE_ROOT="$(cd "$1" && pwd)"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
OUT="$PROJECT_ROOT/backend/profiles/compare_$STAMP"
BENCH_COUNT="${BENCH_COUNT:-5}"
SELECTED="${BENCH:-}"
SIDE_ORDER=(base head head base base head)
PGO_FLAG="$(shipped_pgo_flag "$PROJECT_ROOT")"

if [[ -n $SELECTED ]] && ! benchmark_known "$SELECTED"; then
    echo "unknown benchmark BENCH=$SELECTED, expected one of: ${!FULL_GAME_BENCHMARKS[*]}"
    exit 1
fi

describe_checkout() {
    local root="$1"
    local revision
    revision=$(git -C "$root" rev-parse --short HEAD)
    if [[ -n $(git -C "$root" status --porcelain) ]]; then
        revision="$revision with uncommitted changes"
    fi
    echo "$revision ($root)"
}

side_root() {
    if [[ $1 == base ]]; then
        echo "$BASE_ROOT"
    else
        echo "$PROJECT_ROOT"
    fi
}

run_side() {
    local name="$1"
    local side="$2"
    local package="$3"
    local benchmark="$4"
    local output
    output=$(cd "$(side_root "$side")/backend/game_v2/${package#./}" && "$OUT/$name.$side.test" -test.run '^$' \
        -test.bench "^$benchmark\$" -test.benchmem -test.count "$BENCH_COUNT")
    if ! grep -q "^$benchmark" <<< "$output"; then
        echo "the $side checkout has no $benchmark in $package"
        return 1
    fi
    echo "$output" >> "$OUT/$name.$side.txt"
}

mkdir -p "$OUT"
echo "base: $(describe_checkout "$BASE_ROOT")"
echo "head: $(describe_checkout "$PROJECT_ROOT")"
echo "order: ${SIDE_ORDER[*]}, $BENCH_COUNT runs each, both sides built with head's $PGO_FLAG"
echo ""

for name in "${FULL_GAME_BENCHMARK_ORDER[@]}"; do
    if [[ -n $SELECTED && $name != "$SELECTED" ]]; then
        continue
    fi

    read -r package benchmark <<< "${FULL_GAME_BENCHMARKS[$name]}"
    echo "=== $name: $benchmark ($package) ==="
    for side in base head; do
        go test -C "$(side_root "$side")/backend/game_v2" -c "$PGO_FLAG" -o "$OUT/$name.$side.test" "$package"
    done
    for side in "${SIDE_ORDER[@]}"; do
        echo "  running $side..."
        run_side "$name" "$side" "$package" "$benchmark"
    done
    echo ""
    (cd "$PROJECT_ROOT/backend/game_v2" && go tool benchstat base="$OUT/$name.base.txt" head="$OUT/$name.head.txt")
    echo ""
done

echo "results: $OUT"
