#!/bin/bash

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <binary> <cpu profile>"
    exit 2
fi

BINARY="$1"
PROFILE="$2"
MODULE_PREFIX="github.com/MahjongRepository/ronin/backend/game_v2/"
TOP_NODES=30

top=$(go tool pprof -top -nodecount="$TOP_NODES" "$BINARY" "$PROFILE")
if grep -qE 'Total samples = 0 *$' <<< "$top"; then
    echo "the CPU profile $PROFILE holds no samples"
    exit 1
fi

project=$(go tool pprof -top -cum -nodecount="$TOP_NODES" -show="$MODULE_PREFIX" "$BINARY" "$PROFILE")

echo "CPU profile: $PROFILE"
echo ""
echo "=== top functions by self time ==="
sed "s#$MODULE_PREFIX##g" <<< "$top"
echo ""
echo "=== top project functions by inclusive time (runtime and library time charged to their caller) ==="
sed "/show=/!s#$MODULE_PREFIX##g" <<< "$project"
echo ""
echo "explore: go tool pprof -http=: $PROFILE"
