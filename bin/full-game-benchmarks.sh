#!/bin/bash

declare -A FULL_GAME_BENCHMARKS=(
    [engine]="./internal/replay BenchmarkRun_FullGame"
    [router]="./internal/server BenchmarkRouter_FullGame"
    [socket]="./internal/server BenchmarkSocket_FullGame"
)
FULL_GAME_BENCHMARK_ORDER=(engine router socket)

benchmark_known() {
    [[ -v FULL_GAME_BENCHMARKS[$1] ]]
}

shipped_pgo_flag() {
    local pgo_file="$1/backend/game_v2/cmd/gameserver/default.pgo"
    if [[ -f $pgo_file ]]; then
        echo "-pgo=$pgo_file"
    else
        echo "-pgo=off"
    fi
}
