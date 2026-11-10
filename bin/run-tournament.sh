#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BOT_ROOT="${BOT_ROOT:-$HOME/work/mahjong-bot}"

GAME_PORT=8711
LOBBY_PORT=8710
MAX_RETRIES=10
BOT_EXIT_TIMEOUT=60

OWNER_NAME=tourney_host
TOURNAMENT_NAME="Bot Cup $(date +%Y-%m-%d_%H-%M-%S)"
BOT_NAMES=(ai-tour-1 ai-tour-2 ai-tour-3 ai-tour-4 ai-tour-5 ai-tour-6 ai-tour-7 ai-tour-8)
RUN_LOG_DIR="$PROJECT_ROOT/backend/logs/tournament"

SERVER_PIDS=()
BOT_PIDS=()
BOT_KEYS=()

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
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

wait_for_server() {
    local port="$1"
    local retries=0
    while [[ $retries -lt $MAX_RETRIES ]]; do
        if curl -sf --max-time 5 "http://localhost:$port/health" > /dev/null 2>&1; then
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
    (cd "$PROJECT_ROOT" && uv run --project backend uvicorn --factory "$module" --host 0.0.0.0 --port "$port" \
        --timeout-graceful-shutdown 5 --ws websockets-sansio --ws-per-message-deflate false --ws-ping-interval 20 \
        --ws-ping-timeout 20 --ws-max-size "$ws_max_size" > "$log_dir/stdout.log" 2> "$log_dir/stderr.log") &
    SERVER_PIDS+=($!)
    if ! wait_for_server "$port"; then
        echo "$name server failed to start, see $log_dir"
        exit 1
    fi
}

stop_all() {
    for pid in "${BOT_PIDS[@]}" "${SERVER_PIDS[@]}"; do
        kill_tree "$pid"
    done
    for pid in "${BOT_PIDS[@]}" "${SERVER_PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

register_bots() {
    local output
    local status=0
    output=$(cd "$PROJECT_ROOT" && uv run --project backend python backend/scripts/register_bot.py "${BOT_NAMES[@]}" \
        2>&1) || status=$?
    mapfile -t BOT_KEYS < <(sed -n 's/^API key: //p' <<< "$output")
    if [[ $status -ne 0 || ${#BOT_KEYS[@]} -ne ${#BOT_NAMES[@]} ]]; then
        echo "registering bots failed with status $status:"
        grep -v '^API key: ' <<< "$output" || true
        exit 1
    fi
}

create_tournament() {
    local output
    local status=0
    output=$(cd "$PROJECT_ROOT" && uv run --project backend python backend/scripts/create_tournament.py \
        "$OWNER_NAME" "$TOURNAMENT_NAME" 2>&1) || status=$?
    OWNER_KEY=$(sed -n 's/^API key: //p' <<< "$output")
    TOURNAMENT_ID=$(sed -n 's/^Tournament id: //p' <<< "$output")
    if [[ $status -ne 0 || -z $OWNER_KEY || -z $TOURNAMENT_ID ]]; then
        echo "creating the tournament failed with status $status:"
        grep -v '^API key: ' <<< "$output" || true
        exit 1
    fi
    echo "tournament '$TOURNAMENT_NAME' ($TOURNAMENT_ID) owned by $OWNER_NAME"
}

start_bots() {
    for idx in "${!BOT_NAMES[@]}"; do
        local name="${BOT_NAMES[$idx]}"
        PYTHONPATH="$BOT_ROOT/project" "$BOT_ROOT/.venv/bin/python" "$BOT_ROOT/project/run_ronin.py" \
            -p "$name" -k "${BOT_KEYS[$idx]}" -t "$TOURNAMENT_ID" > "$RUN_LOG_DIR/bots/$name.log" 2>&1 &
        BOT_PIDS+=($!)
    done
}

wait_for_bots() {
    local deadline=$(( $(date +%s) + BOT_EXIT_TIMEOUT ))
    local failed=0
    for idx in "${!BOT_PIDS[@]}"; do
        local pid="${BOT_PIDS[$idx]}"
        while kill -0 "$pid" 2>/dev/null && [[ $(date +%s) -lt $deadline ]]; do
            sleep 1
        done
        local status=0
        if kill -0 "$pid" 2>/dev/null; then
            echo "bot ${BOT_NAMES[$idx]} still running ${BOT_EXIT_TIMEOUT}s after the games ended"
            status=1
        else
            wait "$pid" || status=$?
        fi
        if [[ $status -ne 0 ]]; then
            echo "bot ${BOT_NAMES[$idx]} failed with status $status, see $RUN_LOG_DIR/bots/${BOT_NAMES[$idx]}.log"
            failed=1
        fi
    done

    return $failed
}

trap stop_all EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -f "$PROJECT_ROOT/.env.local" ]; then
    set -a && . "$PROJECT_ROOT/.env.local" && set +a
fi
. "$SCRIPT_DIR/local-settings.sh"
export LOG_LEVEL=info
export LOG_FORMAT=console
export GAME_LOG_DIR="$RUN_LOG_DIR/game"
export LOBBY_LOG_DIR="$RUN_LOG_DIR/lobby"

rm -rf "$RUN_LOG_DIR"
mkdir -p "$GAME_LOG_DIR" "$LOBBY_LOG_DIR" "$RUN_LOG_DIR/bots"

register_bots
create_tournament

free_port "$GAME_PORT"
free_port "$LOBBY_PORT"
start_server game game.server.app:get_app "$GAME_PORT" 262144 "$GAME_LOG_DIR"
start_server lobby lobby.server.app:get_app "$LOBBY_PORT" 8192 "$LOBBY_LOG_DIR"

start_bots

MANAGER_STATUS=0
(cd "$PROJECT_ROOT" && uv run --project backend python bin/tournament_manager.py \
    --lobby-url "http://localhost:$LOBBY_PORT" --tournament "$TOURNAMENT_ID" --api-key "$OWNER_KEY" \
    --log "$RUN_LOG_DIR/manager.log" "${BOT_NAMES[@]}") || MANAGER_STATUS=$?

BOTS_STATUS=0
if [[ $MANAGER_STATUS -eq 0 ]]; then
    wait_for_bots || BOTS_STATUS=1
fi

echo ""
echo "logs in $RUN_LOG_DIR (manager.log holds every API response and event)"
if [[ $MANAGER_STATUS -ne 0 || $BOTS_STATUS -ne 0 ]]; then
    echo "=== tournament run failed ==="
    exit 1
fi
echo "=== tournament run completed ==="
