#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BOT_ROOT="${BOT_ROOT:-$HOME/work/mahjong-bot}"

GAME_LOG_DIR="$PROJECT_ROOT/backend/logs/game"
LOBBY_LOG_DIR="$PROJECT_ROOT/backend/logs/lobby"
BOT_LOG_DIR="$BOT_ROOT/project/logs"

SERVER_ISSUE_PATTERN='\[(warning|error|critical) *\]|Traceback|timeout, auto-'
BOT_ISSUE_PATTERN='ERROR|WARNING|CRITICAL|Traceback'

MAX_ITERATIONS="${1:-10}"

GAME_PORT=8711
LOBBY_PORT=8710
MAX_RETRIES=10
GAME_TIMEOUT=120

SERVER_PIDS=()

kill_tree() {
    local pid="$1"
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
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

cleanup() {
    echo ""
    echo "stopping servers..."
    for pid in "${SERVER_PIDS[@]}"; do
        kill_tree "$pid"
        wait "$pid" 2>/dev/null || true
    done
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

    echo "starting $name server on port $port..."
    cd "$PROJECT_ROOT" && uv run --project backend uvicorn --factory "$module" --host 0.0.0.0 --port "$port" --timeout-graceful-shutdown 5 --ws websockets-sansio --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size "$ws_max_size" > /dev/null 2>&1 &
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
    matches=$(grep -rnE "$pattern" "$dir" 2>/dev/null || true)
    if [[ -z "$matches" ]]; then
        return 0
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
    game_ids=$(grep -rhoE 'Game started, game_id=[0-9a-f-]+' "$BOT_LOG_DIR" 2>/dev/null | sed 's/.*game_id=//' | sort -u || true)

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

trap cleanup EXIT INT TERM

find "$PROJECT_ROOT/backend/data/replays" "$PROJECT_ROOT/backend/data/tenhou_replays" -mindepth 1 -delete 2>/dev/null || true
for dir in "$GAME_LOG_DIR" "$LOBBY_LOG_DIR" "$BOT_LOG_DIR"; do
    find "$dir" -mindepth 1 -delete 2>/dev/null || true
done

if [ -f "$PROJECT_ROOT/.env.local" ]; then
    set -a && . "$PROJECT_ROOT/.env.local" && set +a
fi
. "$SCRIPT_DIR/local-settings.sh"

free_port "$GAME_PORT"
free_port "$LOBBY_PORT"
start_server "game" "game.server.app:get_app" "$GAME_PORT" 262144
start_server "lobby" "lobby.server.app:get_app" "$LOBBY_PORT" 8192

echo ""
echo "running $MAX_ITERATIONS game(s)..."
echo ""

TOTAL_START=$(date +%s)

for i in $(seq 1 "$MAX_ITERATIONS"); do
    echo "=== Game $i/$MAX_ITERATIONS ==="

    GAME_START=$(date +%s)

    make -C "$BOT_ROOT" run-ronin-matchmaking > /dev/null 2>&1 &
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

echo "=== all $MAX_ITERATIONS game(s) completed successfully ==="
print_stats
