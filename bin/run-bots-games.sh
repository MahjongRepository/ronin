#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BOT_ROOT="${BOT_ROOT:-$HOME/work/mahjong-bot}"

BOT_LOG_DIR="$BOT_ROOT/project/logs"

PYTHON_WARNING_PATTERN=':[0-9]+: [A-Za-z]*Warning: '
SERVER_ISSUE_PATTERN="\\[(warning|error|critical) *\\]|^(WARNING|ERROR|CRITICAL):|Traceback|$PYTHON_WARNING_PATTERN|timeout, auto-|auth timeout,|replaced player with AI|player reconnected|connection taken over|stale game action"
BOT_CONSOLE_NOISE_PATTERN='^(.\[[0-9]+m)?[0-9-]{10} [0-9:,]{8,12} [^ ]+ (DEBUG|INFO): '
BOT_ISSUE_PATTERN="ERROR|WARNING|CRITICAL|Traceback|$PYTHON_WARNING_PATTERN"

MAX_ITERATIONS="${1:-10}"

GAME_PORT=8711
LOBBY_PORT=8710
MAX_RETRIES=10
GAME_TIMEOUT=120
SHUTDOWN_TIMEOUT=15

SERVER_PIDS=()

kill_tree() {
    local pid="$1"
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
}

list_tree() {
    local pid="$1"
    echo "$pid"
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        list_tree "$child"
    done
}

wait_for_exit() {
    local exited=0
    local deadline=$(( $(date +%s) + SHUTDOWN_TIMEOUT ))
    for pid in "$@"; do
        while kill -0 "$pid" 2>/dev/null; do
            if [[ $(date +%s) -ge $deadline ]]; then
                echo "process $pid still running ${SHUTDOWN_TIMEOUT}s after stop, killing it"
                kill -9 "$pid" 2>/dev/null || true
                exited=1
                break
            fi
            sleep 0.1
        done
    done

    return $exited
}

free_port() {
    local port="$1"
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

stop_servers() {
    if [[ ${#SERVER_PIDS[@]} -eq 0 ]]; then
        return 0
    fi

    echo ""
    echo "stopping servers..."
    local server_tree=()
    for pid in "${SERVER_PIDS[@]}"; do
        server_tree+=($(list_tree "$pid"))
    done

    for pid in "${SERVER_PIDS[@]}"; do
        kill_tree "$pid"
        wait "$pid" 2>/dev/null || true
    done
    local exited=0
    wait_for_exit "${server_tree[@]}" || exited=1
    SERVER_PIDS=()

    return $exited
}

wait_for_server() {
    local port="$1"
    local retries=0

    while [[ $retries -lt $MAX_RETRIES ]]; do
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            return 0
        fi
        retries=$((retries + 1))
        sleep 1
    done

    return 1
}

start_server() {
    local name="$1"
    local module="$2"
    local port="$3"
    local ws_max_size="$4"
    local log_dir="$5"

    echo "starting $name server on port $port..."
    cd "$PROJECT_ROOT" && uv run --project backend uvicorn --factory "$module" --host 0.0.0.0 --port "$port" --timeout-graceful-shutdown 5 --ws websockets-sansio --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size "$ws_max_size" > /dev/null 2> "$log_dir/stderr.log" &
    SERVER_PIDS+=($!)

    if ! wait_for_server "$port" || ! kill -0 "${SERVER_PIDS[-1]}" 2>/dev/null; then
        echo "$name server failed to start after $MAX_RETRIES retries"
        exit 1
    fi
    echo "$name server ready"
}

scan_logs() {
    local label="$1"
    local dir="$2"
    local pattern="$3"

    local matches
    local status=0
    matches=$(grep -rnaE "$pattern" "$dir") || status=$?
    if [[ $status -eq 1 ]]; then
        return 0
    fi

    if [[ $status -ne 0 ]]; then
        echo "=== $label LOGS ($dir): grep failed with status $status ==="
        return 1
    fi

    echo "=== $label LOGS ($dir) ==="
    echo "$matches"
    echo ""
    return 1
}

analyze_logs() {
    local has_issues=0

    scan_logs GAME "$GAME_LOG_DIR" "$SERVER_ISSUE_PATTERN" || has_issues=1
    scan_logs LOBBY "$LOBBY_LOG_DIR" "$SERVER_ISSUE_PATTERN" || has_issues=1
    scan_logs BOT "$BOT_LOG_DIR" "$BOT_ISSUE_PATTERN" || has_issues=1

    return $has_issues
}

verify_games() {
    local expected_count="$1"

    local game_ids
    game_ids=$(grep -rhoaE 'Game started, game_id=[0-9a-f-]+' "$BOT_LOG_DIR" 2>/dev/null | sed 's/.*game_id=//' | sort -u || true)

    local count
    count=$(echo "$game_ids" | grep -c . || true)
    if [[ $count -ne $expected_count ]]; then
        echo "bots played $count game(s), expected $expected_count"
        return 1
    fi

    # shellcheck disable=SC2086
    (cd "$PROJECT_ROOT" && uv run --project backend python bin/verify_games.py $game_ids)
}

GAME_TIMES=()
TOTAL_START=0

print_stats() {
    if [[ ${#GAME_TIMES[@]} -eq 0 ]]; then
        return
    fi

    local total_elapsed=$(( $(date +%s) - TOTAL_START ))
    local sum=0
    for t in "${GAME_TIMES[@]}"; do
        sum=$((sum + t))
    done
    local avg=$((sum / ${#GAME_TIMES[@]}))

    echo ""
    echo "--- stats ---"
    for idx in "${!GAME_TIMES[@]}"; do
        echo "  game $((idx + 1)): ${GAME_TIMES[$idx]}s"
    done
    echo ""
    echo "  total: ${total_elapsed}s"
    echo "  avg per game: ${avg}s"
}

filter_bot_console() {
    local raw_file="$1"
    local console_file="$2"

    local status=0
    grep -vaE "$BOT_CONSOLE_NOISE_PATTERN" "$raw_file" > "$console_file" || status=$?
    if [[ $status -gt 1 ]]; then
        echo "filtering bot console output failed with status $status"
        return 1
    fi

    rm "$raw_file"
}

trap stop_servers EXIT INT TERM

if [ -f "$PROJECT_ROOT/.env.local" ]; then
    set -a && . "$PROJECT_ROOT/.env.local" && set +a
fi
. "$SCRIPT_DIR/local-settings.sh"
export LOG_LEVEL=debug
export LOG_FORMAT=console
export GAME_LOG_DIR="$PROJECT_ROOT/backend/logs/game"
export LOBBY_LOG_DIR="$PROJECT_ROOT/backend/logs/lobby"

find "$PROJECT_ROOT/backend/data/replays" "$PROJECT_ROOT/backend/data/tenhou_replays" -mindepth 1 -delete 2>/dev/null || true
for dir in "$GAME_LOG_DIR" "$LOBBY_LOG_DIR" "$BOT_LOG_DIR"; do
    find "$dir" -mindepth 1 -delete 2>/dev/null || true
    mkdir -p "$dir"
done

free_port "$GAME_PORT"
free_port "$LOBBY_PORT"
start_server "game" "game.server.app:get_app" "$GAME_PORT" 262144 "$GAME_LOG_DIR"
start_server "lobby" "lobby.server.app:get_app" "$LOBBY_PORT" 8192 "$LOBBY_LOG_DIR"

echo ""
echo "running $MAX_ITERATIONS game(s)..."
echo ""

TOTAL_START=$(date +%s)

for i in $(seq 1 "$MAX_ITERATIONS"); do
    echo "=== Game $i/$MAX_ITERATIONS ==="

    GAME_START=$(date +%s)

    BOT_CONSOLE_RAW="$BOT_LOG_DIR/console-$i.raw"
    make -C "$BOT_ROOT" run-ronin-matchmaking > "$BOT_CONSOLE_RAW" 2>&1 &
    BOT_PID=$!
    ELAPSED=0

    while kill -0 "$BOT_PID" 2>/dev/null; do
        if [[ $ELAPSED -ge $GAME_TIMEOUT ]]; then
            echo "game timed out after ${GAME_TIMEOUT}s, stopping"
            kill_tree "$BOT_PID"
            wait "$BOT_PID" 2>/dev/null || true
            print_stats
            exit 1
        fi
        if ! curl -sf "http://localhost:$GAME_PORT/health" > /dev/null 2>&1 ||
           ! curl -sf "http://localhost:$LOBBY_PORT/health" > /dev/null 2>&1; then
            echo "server health check failed, stopping"
            kill_tree "$BOT_PID"
            wait "$BOT_PID" 2>/dev/null || true
            print_stats
            exit 1
        fi
        sleep 1
        ELAPSED=$((ELAPSED + 1))
    done

    BOT_EXIT=0
    wait "$BOT_PID" || BOT_EXIT=$?

    GAME_END=$(date +%s)
    GAME_ELAPSED=$((GAME_END - GAME_START))
    GAME_TIMES+=("$GAME_ELAPSED")

    if [[ $BOT_EXIT -ne 0 ]]; then
        echo "bot exited with code $BOT_EXIT, stopping"
        print_stats
        exit 1
    fi

    filter_bot_console "$BOT_CONSOLE_RAW" "$BOT_LOG_DIR/console-$i.log"

    if ! verify_games "$i"; then
        echo ""
        echo "game $i failed verification, stopping"
        print_stats
        exit 1
    fi

    if ! analyze_logs; then
        echo ""
        echo "issues found in game $i, stopping"
        print_stats
        exit 1
    fi

    echo "clean (${GAME_ELAPSED}s)"
    echo ""
done

if ! stop_servers || ! analyze_logs; then
    echo ""
    echo "issues found during server shutdown"
    print_stats
    exit 1
fi

echo "=== all $MAX_ITERATIONS game(s) completed successfully ==="
print_stats
