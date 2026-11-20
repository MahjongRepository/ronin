#!/bin/bash

# Run game server, Vite dev server, and lobby server together.
# Ctrl+C stops all servers.

set -e

GAME_PORT=${GAME_PORT:-8712}
LOBBY_PORT=${LOBBY_PORT:-8710}
VITE_PORT=${VITE_PORT:-5173}
GAME_V2_VITE_PORT=${GAME_V2_VITE_PORT:-5175}
MAX_RETRIES=10
DOCKER=${DOCKER:-}

case "$DOCKER" in
    "") OWN_PORTS="$GAME_PORT $LOBBY_PORT $VITE_PORT $GAME_V2_VITE_PORT" ;;
    1) OWN_PORTS="$LOBBY_PORT $VITE_PORT $GAME_V2_VITE_PORT" ;;
    *)
        echo "unknown DOCKER=$DOCKER, expected 1 or nothing"
        exit 1
        ;;
esac

# Kill any already-running servers on our ports
for port in $GAME_PORT $LOBBY_PORT $VITE_PORT $GAME_V2_VITE_PORT; do
    pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
done

port_taken() {
    (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null
}

for port in $OWN_PORTS; do
    for _ in $(seq 1 10); do
        port_taken "$port" || continue 2
        sleep 0.2
    done
    echo "Error: port $port is still in use by a process this user cannot see or kill"
    exit 1
done

if [ -f .env.local ]; then
    set -a && . .env.local && set +a
fi
if [ "$DOCKER" = 1 ]; then
    export LOBBY_REPLAY_DIR="backend/data/game-v2-replays"
fi
. "$(dirname "$0")/local-settings.sh"

kill_tree() {
    local pid="$1"
    # kill children first, then the process itself
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
}

wait_for_server() {
    local port="$1"
    local pid="$2"
    local retries=0

    while [ $retries -lt $MAX_RETRIES ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 1
        fi
        if curl -sf --max-time 2 "http://localhost:$port/health" > /dev/null 2>&1; then
            return 0
        fi
        retries=$((retries + 1))
        sleep 1
    done

    return 1
}

# Enable Vite dev mode in the lobby backend
export LOBBY_VITE_DEV_URL="http://localhost:${VITE_PORT}"
export LOBBY_GAME_CLIENT_V2_DEV_URL="http://localhost:${GAME_V2_VITE_PORT}"

CLEANING_UP=false
GAME_CONTAINER_STARTED=false
cleanup() {
    if $CLEANING_UP; then
        return
    fi
    CLEANING_UP=true
    trap - EXIT INT TERM
    echo "Stopping servers..."
    if [ -n "$GAME_PID" ]; then
        kill_tree "$GAME_PID"
    fi
    if [ -n "$VITE_PID" ]; then
        kill_tree "$VITE_PID"
    fi
    if [ -n "$GAME_V2_VITE_PID" ]; then
        kill_tree "$GAME_V2_VITE_PID"
    fi
    if [ -n "$GAME_BUILD_DIR" ]; then
        rm -rf "$GAME_BUILD_DIR"
    fi
    if $GAME_CONTAINER_STARTED; then
        make -s stop-game-v2-docker
    fi
}

trap cleanup EXIT INT TERM

# Set lobby settings for template rendering
export LOBBY_GAME_CLIENT_URL="/play"

start_game_server() {
    echo "Building the Go game server..."
    GAME_BUILD_DIR=$(mktemp -d)
    go build -C backend/game_v2 -o "$GAME_BUILD_DIR/gameserver" ./cmd/gameserver

    echo "Starting game server on port $GAME_PORT..."
    "$GAME_BUILD_DIR/gameserver" -addr "0.0.0.0:$GAME_PORT" &
    GAME_PID=$!

    echo "Waiting for game server to be ready..."
    if ! wait_for_server $GAME_PORT $GAME_PID; then
        echo "Error: Game server failed to start; see its output above"
        exit 1
    fi
}

start_game_container() {
    echo "Starting the game server container on port $GAME_PORT..."
    GAME_CONTAINER_STARTED=true
    if ! make -s run-game-v2-docker; then
        echo "Error: the game server container failed to start; see its output above"
        exit 1
    fi
}

if [ "$DOCKER" = 1 ]; then
    start_game_container
else
    start_game_server
fi

echo "Starting lobby Vite dev server on port $VITE_PORT..."
(cd frontend/lobby && VITE_PORT=$VITE_PORT npm run dev) &
VITE_PID=$!

echo "Starting game client v2 Vite dev server on port $GAME_V2_VITE_PORT..."
(cd frontend/game_v2 && GAME_V2_VITE_PORT=$GAME_V2_VITE_PORT npm run dev) &
GAME_V2_VITE_PID=$!

sleep 2
if ! kill -0 "$VITE_PID" 2>/dev/null; then
    echo "Error: lobby Vite dev server failed to start"
    exit 1
fi
if ! kill -0 "$GAME_V2_VITE_PID" 2>/dev/null; then
    echo "Error: game client v2 Vite dev server failed to start"
    exit 1
fi

echo "Starting lobby server on port $LOBBY_PORT..."
echo "Open http://localhost:$LOBBY_PORT in your browser"
uv run --project backend uvicorn --factory lobby.server.app:get_app --reload --host 0.0.0.0 --port $LOBBY_PORT --timeout-graceful-shutdown 5 --ws websockets-sansio --ws-per-message-deflate false --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size 8192
