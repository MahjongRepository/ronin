#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BOT_ROOT="${BOT_ROOT:-$HOME/work/mahjong-bot}"
BOT_BIN="${BOT_BIN:-}"
PORTAL="${PORTAL:-}"
PORTAL_RUN_TIMEOUT="${PORTAL_RUN_TIMEOUT:-3600}"
PORTAL_URL="${PORTAL_URL:-http://127.0.0.1:8060}"
PORTAL_SERVER_DIR="${PORTAL_SERVER_DIR:-$HOME/work/mahjong-portal/server}"
PANTHEON_MIMIR_URL="${PANTHEON_MIMIR_URL:-http://127.0.0.1:4001}"
PANTHEON_MIMIR_HOST="${PANTHEON_MIMIR_HOST:-mimir.pantheon.local}"

GAME_PORT="${GAME_PORT:-8711}"
LOBBY_PORT="${LOBBY_PORT:-8710}"
MAX_RETRIES=10
BOT_EXIT_TIMEOUT=60

OWNER_NAME=tourney_host
TOURNAMENT_NAME="Bot Cup $(date +%Y-%m-%d_%H-%M-%S)"
BOT_NAMES=(ai-tour-1 ai-tour-2 ai-tour-3 ai-tour-4 ai-tour-5 ai-tour-6 ai-tour-7 ai-tour-8)
RUN_LOG_DIR="$PROJECT_ROOT/backend/logs/tournament"
PORTAL_ROUNDS=4
if [[ -n $PORTAL ]]; then
    BOT_NAMES=(ai-pt-1 ai-pt-2 ai-pt-3 ai-pt-4 ai-pt-5 ai-pt-6 ai-pt-7 ai-pt-8)
    PORTAL_NAMES=(ai-pt-1 ai-pt-2 AI-PT-3 ai-pt-4 ai-pt-5 ai-pt-6 ai-pt-7 ai-pt-8)
    RUN_LOG_DIR="$PROJECT_ROOT/backend/logs/portal-tournament"
fi

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

build_bot() {
    if [[ -n $BOT_BIN ]]; then
        return 0
    fi

    if ! make -sC "$BOT_ROOT" release-bot; then
        echo "building the bot in $BOT_ROOT failed"
        exit 1
    fi
    BOT_BIN="$BOT_ROOT/rust/target/release/mahjong-bot"
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
        "$BOT_BIN" -p "$name" -k "${BOT_KEYS[$idx]}" --lobby-url "http://localhost:$LOBBY_PORT" \
            -t "$TOURNAMENT_ID" > "$RUN_LOG_DIR/bots/$name.log" 2>&1 &
        BOT_PIDS+=($!)
    done
}

relaunch_bot() {
    local name="$1"
    local key="$2"
    local launch=0
    while true; do
        launch=$((launch + 1))
        local status=0
        echo "=== launch $launch" >> "$RUN_LOG_DIR/bots/$name.log"
        "$BOT_BIN" -p "$name" -k "$key" --lobby-url "http://localhost:$LOBBY_PORT" -t "$TOURNAMENT_ID" \
            >> "$RUN_LOG_DIR/bots/$name.log" 2>&1 || status=$?
        echo "=== launch $launch exited with status $status" >> "$RUN_LOG_DIR/bots/$name.log"
        sleep 1
    done
}

start_relaunching_bots() {
    for idx in "${!BOT_NAMES[@]}"; do
        relaunch_bot "${BOT_NAMES[$idx]}" "${BOT_KEYS[$idx]}" &
        BOT_PIDS+=($!)
    done
}

register_on_portal() {
    local output
    local status=0
    output=$(cd "$PORTAL_SERVER_DIR" && uv run --env-file ../.envs/.local-sqlite python manage.py setup_ronin_e2e \
        --ronin-tournament-id "$TOURNAMENT_ID" --games-start-in 60 "${PORTAL_NAMES[@]}" 2> "$RUN_LOG_DIR/portal-setup.log") || status=$?
    PORTAL_TOURNAMENT_ID=$(sed -n 's/^PORTAL_TOURNAMENT_ID=//p' <<< "$output")
    PORTAL_LOBBY_ID=$(sed -n 's/^PORTAL_LOBBY_ID=//p' <<< "$output")
    PANTHEON_EVENT_ID=$(sed -n 's/^PANTHEON_EVENT_ID=//p' <<< "$output")
    if [[ $status -ne 0 || -z $PORTAL_TOURNAMENT_ID || -z $PORTAL_LOBBY_ID || -z $PANTHEON_EVENT_ID ]]; then
        echo "setting up the portal tournament failed with status $status, see $RUN_LOG_DIR/portal-setup.log"
        exit 1
    fi
    export PORTAL_TOURNAMENT_ID PORTAL_LOBBY_ID PANTHEON_EVENT_ID
    echo "portal tournament $PORTAL_TOURNAMENT_ID, lobby $PORTAL_LOBBY_ID, Pantheon event $PANTHEON_EVENT_ID"
}

check_pantheon_games() {
    local expected="$1"
    curl -sf --max-time 10 -H "Host: $PANTHEON_MIMIR_HOST" -H "Content-Type: application/json" \
        -d "{\"eventIdList\": [$PANTHEON_EVENT_ID], \"limit\": 100, \"offset\": 0}" \
        "$PANTHEON_MIMIR_URL/v2/common.Mimir/GetLastGames" \
        | python3 -c '
import json, sys
expected = int(sys.argv[1])
total = json.load(sys.stdin).get("totalGames", 0)
print(f"pantheon event games: {total}, expected: {expected}")
sys.exit(0 if total == expected else 1)
' "$expected"
}

check_ronin_games() {
    local expected="$1"
    curl -sf --max-time 10 -H "X-API-Key: $OWNER_KEY" "http://localhost:$LOBBY_PORT/api/tournaments/$TOURNAMENT_ID" \
        | python3 -c '
import json, sys
expected = int(sys.argv[1])
games = json.load(sys.stdin)["games"]
completed = sum(game["end_reason"] == "completed" for game in games)
print(f"ronin games: {len(games)}, completed: {completed}, expected completed: {expected}")
sys.exit(0 if completed == len(games) == expected else 1)
' "$expected"
}

portal() {
    (cd "$PROJECT_ROOT" && uv run --project backend python bin/tournament.py "$@") 2>&1 \
        | tee -a "$RUN_LOG_DIR/tournament.log"
}

require_portal_env() {
    : "${PORTAL_API_TOKEN:?PORTAL_API_TOKEN is not set}"
    export PORTAL_URL PORTAL_API_TOKEN
}

run_portal_tournament() {
    export RONIN_URL="http://localhost:$LOBBY_PORT"
    export RONIN_TOURNAMENT_ID="$TOURNAMENT_ID"
    export RONIN_API_KEY="$OWNER_KEY"

    register_on_portal
    portal open-registration
    for name in "${PORTAL_NAMES[@]}"; do
        portal confirm "$name"
    done
    portal close-registration

    start_relaunching_bots

    local run_status=0
    (cd "$PROJECT_ROOT" && timeout "$PORTAL_RUN_TIMEOUT" uv run --project backend python bin/tournament.py run) \
        > "$RUN_LOG_DIR/tournament-run.log" 2>&1 || run_status=$?
    echo "tournament.py run exited with status $run_status"

    local games=$(( ${#BOT_NAMES[@]} / 4 * PORTAL_ROUNDS ))
    local ronin_status=0
    check_ronin_games "$games" || ronin_status=1
    local pantheon_status=0
    check_pantheon_games "$games" || pantheon_status=1

    echo ""
    echo "logs in $RUN_LOG_DIR (tournament-run.log holds every portal call, Ronin call and event)"
    if [[ $run_status -ne 0 || $ronin_status -ne 0 || $pantheon_status -ne 0 ]]; then
        echo "=== portal tournament run failed ==="
        exit 1
    fi
    echo "=== portal tournament run completed ==="
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
if [[ -n $PORTAL ]]; then
    require_portal_env
    export AUTH_DATABASE_PATH="$RUN_LOG_DIR/data/storage.db"
    export LOBBY_REPLAY_DIR="$RUN_LOG_DIR/data/replays"
    export GAME_REPLAY_DIR="$RUN_LOG_DIR/data/replays"
    export LOBBY_METRICS_DB_PATH="$RUN_LOG_DIR/data/metrics.db"
    export LOBBY_WS_ALLOWED_ORIGIN="http://localhost:$LOBBY_PORT"
    export LOBBY_GAME_SERVER_URL="http://localhost:$GAME_PORT"
    export LOBBY_GAME_SERVER_WS_URL="ws://localhost:$GAME_PORT"
    unset LOBBY_VITE_DEV_URL LOBBY_GAME_CLIENT_V2_DEV_URL
fi

build_bot

rm -rf "$RUN_LOG_DIR"
mkdir -p "$GAME_LOG_DIR" "$LOBBY_LOG_DIR" "$RUN_LOG_DIR/bots" "$RUN_LOG_DIR/data/replays"

register_bots
create_tournament

free_port "$GAME_PORT"
free_port "$LOBBY_PORT"
start_server game game.server.app:get_app "$GAME_PORT" 262144 "$GAME_LOG_DIR"
start_server lobby lobby.server.app:get_app "$LOBBY_PORT" 8192 "$LOBBY_LOG_DIR"

if [[ -n $PORTAL ]]; then
    run_portal_tournament
    exit 0
fi

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
