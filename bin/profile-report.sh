#!/bin/bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <profile dir>"
    exit 2
fi

DIR="$1"
CPU_PROFILE="$DIR/cpu.prof"
ALLOCS_PROFILE="$DIR/allocs.prof"
MUTEX_PROFILE="$DIR/mutex.prof"
RUNTIME_STATS="$DIR/runtime.json"
GAMES="${GAMES:-}"
MODULE_PREFIX="github.com/MahjongRepository/ronin/backend/game_v2/"
GC_FRAMES='^runtime[.](gcBgMarkWorker|gcAssistAlloc|bgsweep|bgscavenge)'
TOP_NODES=30
ALLOC_NODES=20
MUTEX_NODES=15

strip_module() {
    sed "/show=/!s#$MODULE_PREFIX##g"
}

print_layers() {
    go tool pprof -traces "$CPU_PROFILE" | awk -v prefix="$MODULE_PREFIX" -v gc="$GC_FRAMES" '
        function seconds(v) {
            if (v ~ /ns$/) return v / 1e9
            if (v ~ /(us|µs)$/) return v / 1e6
            if (v ~ /ms$/) return v / 1e3
            if (v ~ /mins$/) return v * 60
            if (v ~ /hrs$/) return v * 3600
            return v + 0
        }
        function package_of(name,   rest, slash, at, dot) {
            rest = name
            slash = 0
            while ((at = index(rest, "/")) > 0) {
                slash += at
                rest = substr(rest, at + 1)
            }
            dot = index(rest, ".")
            return dot ? substr(name, 1, slash + dot - 1) : name
        }
        function flush(   i, layer) {
            if (frames == 0) return
            layer = ""
            for (i = 1; i <= frames; i++) {
                if (frame[i] ~ gc) {
                    layer = "runtime GC"
                    break
                }
            }
            for (i = 1; layer == "" && i <= frames; i++) {
                if (index(frame[i], prefix) == 1) layer = package_of(substr(frame[i], length(prefix) + 1))
            }
            if (layer == "") layer = package_of(frame[1]) " (no project frame)"
            total[layer] += value
            frames = 0
        }
        /^-+\+-+$/ { flush(); in_trace = 1; next }
        !in_trace { next }
        /^ +[0-9.]+[a-zµ]+ +[^ ]/ { value = seconds($1); frames = 1; frame[1] = $2; next }
        /^ +[^ ]/ { frame[++frames] = $1 }
        END {
            flush()
            for (layer in total) printf "%.6f\t%s\n", total[layer], layer
        }' | sort -t$'\t' -k1,1nr | awk -F'\t' '
        { value[NR] = $1; layer[NR] = $2; sum += $1 }
        END {
            printf "  %6s  %9s  %s\n", "share", "CPU", "layer"
            for (i = 1; i <= NR; i++) printf "  %5.1f%%  %8.2fs  %s\n", 100 * value[i] / sum, value[i], layer[i]
        }'
}

print_runtime_stats() {
    awk -v games="$GAMES" '
        {
            gsub(/[",{} ]/, "")
            if (split($0, field, ":") == 2) value[field[1]] = field[2]
        }
        END {
            split("busy_cpu_seconds gc_cpu_seconds gc_cycles alloc_bytes alloc_objects mutex_wait_seconds", keys, " ")
            for (i in keys) if (!(keys[i] in value)) exit 1
            busy = value["busy_cpu_seconds"]
            printf "  CPU: %.2fs busy, of which GC %.2fs (%.1f%%) over %d cycle(s)\n",
                busy, value["gc_cpu_seconds"], 100 * value["gc_cpu_seconds"] / (busy > 0 ? busy : 1), value["gc_cycles"]
            printf "  allocated: %.1f MB in %d object(s)\n", value["alloc_bytes"] / 1e6, value["alloc_objects"]
            printf "  mutex wait: %.3fs\n", value["mutex_wait_seconds"]
            if (games > 0) {
                printf "  per game: %.3fs busy CPU, %.1f MB and %d object(s) allocated\n",
                    busy / games, value["alloc_bytes"] / 1e6 / games, value["alloc_objects"] / games
            }
        }' "$RUNTIME_STATS"
}

top=$(go tool pprof -top -nodecount="$TOP_NODES" "$CPU_PROFILE")
if grep -qE 'Total samples = 0 *$' <<< "$top"; then
    echo "the CPU profile $CPU_PROFILE holds no samples"
    exit 1
fi

echo "profiles: $DIR"
echo ""
echo "=== CPU by layer (each sample charged to its deepest project package, GC work on its own row) ==="
print_layers
echo ""
echo "=== top functions by self CPU ==="
strip_module <<< "$top"
echo ""
echo "=== top project functions by inclusive CPU (runtime and library time charged to their caller) ==="
go tool pprof -top -cum -nodecount="$TOP_NODES" -show="$MODULE_PREFIX" "$CPU_PROFILE" | strip_module

if [[ -f $ALLOCS_PROFILE ]]; then
    echo ""
    echo "=== top functions by allocated bytes ==="
    go tool pprof -sample_index=alloc_space -top -nodecount="$ALLOC_NODES" "$ALLOCS_PROFILE" | strip_module
    echo ""
    echo "=== top project functions by allocated objects, inclusive ==="
    go tool pprof -sample_index=alloc_objects -top -cum -nodecount="$ALLOC_NODES" -show="$MODULE_PREFIX" \
        "$ALLOCS_PROFILE" | strip_module
fi

if [[ -f $MUTEX_PROFILE ]]; then
    echo ""
    echo "=== mutex contention by delay ==="
    go tool pprof -top -nodecount="$MUTEX_NODES" "$MUTEX_PROFILE" | strip_module
fi

if [[ -f $RUNTIME_STATS ]]; then
    echo ""
    echo "=== runtime totals (runtime/metrics) ==="
    if ! print_runtime_stats; then
        echo "the runtime stats $RUNTIME_STATS are incomplete"
        exit 1
    fi
fi

echo ""
echo "explore: go tool pprof -http=: $CPU_PROFILE"
