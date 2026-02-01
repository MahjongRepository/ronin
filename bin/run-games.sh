#!/bin/bash

# Start servers, run the bot in a loop, analyze logs after each game,
# stop on first issue, then shut down servers.
#
# Usage: ./bin/run-games.sh [max_iterations]
# Default: max_iterations=10

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

LOG_DIRS=(
    "$PROJECT_ROOT/logs/game:GAME"
    "$PROJECT_ROOT/logs/lobby:LOBBY"
    "$PROJECT_ROOT/bot/project/logs:BOT"
)

MAX_ITERATIONS="${1:-10}"

GAME_PORT=8001
LOBBY_PORT=8000
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

    echo "starting $name server on port $port..."
    cd "$PROJECT_ROOT" && uv run uvicorn "$module" --host 0.0.0.0 --port "$port" > /dev/null 2>&1 &
    SERVER_PIDS+=($!)

    if ! wait_for_server "$port"; then
        echo "$name server failed to start after $MAX_RETRIES retries"
        exit 1
    fi
    echo "$name server ready"
}

# Scan all log dirs for ERROR, WARNING, or Traceback.
# Returns 0 if clean, 1 if issues found.
analyze_logs() {
    local has_issues=0

    for entry in "${LOG_DIRS[@]}"; do
        local dir="${entry%%:*}"
        local label="${entry##*:}"

        local matches
        matches=$(grep -rnE 'ERROR|WARNING|Traceback' "$dir" 2>/dev/null || true)

        if [[ -n "$matches" ]]; then
            has_issues=1
            echo "=== $label LOGS ($dir) ==="
            echo "$matches"
            echo ""
        fi
    done

    if [[ $has_issues -eq 1 ]]; then
        return 1
    fi

    for entry in "${LOG_DIRS[@]}"; do
        rm -f "${entry%%:*}"/*.log
    done
    return 0
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

start_server "game" "game.server.app:app" "$GAME_PORT"
start_server "lobby" "lobby.server.app:app" "$LOBBY_PORT"

echo ""
echo "running $MAX_ITERATIONS game(s)..."
echo ""

TOTAL_START=$(date +%s)

for i in $(seq 1 "$MAX_ITERATIONS"); do
    echo "=== Game $i/$MAX_ITERATIONS ==="

    GAME_START=$(date +%s)

    make -C "$PROJECT_ROOT/bot" run > /dev/null 2>&1 &
    BOT_PID=$!
    ELAPSED=0

    # Wait for bot to finish, but abort on timeout or server health failure.
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

    wait "$BOT_PID"
    BOT_EXIT=$?
    if [[ $BOT_EXIT -ne 0 ]]; then
        echo "bot exited with non-zero code, stopping"
        print_stats
        exit 1
    fi

    GAME_END=$(date +%s)
    GAME_ELAPSED=$((GAME_END - GAME_START))
    GAME_TIMES+=("$GAME_ELAPSED")

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
