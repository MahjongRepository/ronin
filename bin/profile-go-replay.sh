#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROFILE_DIR="$PROJECT_ROOT/backend/profiles"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
BINARY="$PROFILE_DIR/go_replay_$STAMP.test"
PROFILE="$PROFILE_DIR/go_replay_$STAMP.cpu.prof"
BENCH_COUNT="${BENCH_COUNT:-10}"

mkdir -p "$PROFILE_DIR"
echo "replaying the full game fixture through the Go engine, $BENCH_COUNT benchmark runs..."
go test -C "$PROJECT_ROOT/backend/game_v2" -run '^$' -bench '^BenchmarkRun_FullGame$' -benchmem \
    -count "$BENCH_COUNT" -cpuprofile "$PROFILE" -o "$BINARY" ./internal/replay
echo ""
bash "$SCRIPT_DIR/go-profile-report.sh" "$BINARY" "$PROFILE"
