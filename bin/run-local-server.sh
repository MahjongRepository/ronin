#!/bin/bash

# Run game server, Vite dev server, and lobby server together.
# Ctrl+C stops all servers.

set -e

GAME_PORT=${GAME_PORT:-8711}
LOBBY_PORT=${LOBBY_PORT:-8710}
VITE_PORT=${VITE_PORT:-5173}
MAX_RETRIES=10

# Kill any already-running servers on our ports
for port in $GAME_PORT $LOBBY_PORT $VITE_PORT; do
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
done

if [ -f .env.local ]; then
    set -a && . .env.local && set +a
fi

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
    local retries=0

    while [ $retries -lt $MAX_RETRIES ]; do
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            return 0
        fi
        retries=$((retries + 1))
        sleep 1
    done

    return 1
}

CONFIG_DIR=$(mktemp -d)
CONFIG_FILE="$CONFIG_DIR/servers.yaml"
cat > "$CONFIG_FILE" <<EOF
servers:
  - name: "local-1"
    url: "http://localhost:$GAME_PORT"
EOF
export LOBBY_CONFIG_PATH="$CONFIG_FILE"

# Enable Vite dev mode in the lobby backend
export LOBBY_VITE_DEV_URL="http://localhost:${VITE_PORT}"
# Override VITE_LOBBY_URL so the game client points to the correct lobby port
export VITE_LOBBY_URL="http://localhost:${LOBBY_PORT}"

CLEANING_UP=false
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
    rm -rf "$CONFIG_DIR"
}

trap cleanup EXIT INT TERM

# Set lobby settings for template rendering
export LOBBY_GAME_CLIENT_URL="/game"
# Override the default ws_allowed_origin to match the local lobby port
export LOBBY_WS_ALLOWED_ORIGIN="http://localhost:$LOBBY_PORT"

echo "Starting game server on port $GAME_PORT..."
uv run uvicorn --factory game.server.app:get_app --reload --host 0.0.0.0 --port $GAME_PORT &
GAME_PID=$!

echo "Waiting for game server to be ready..."
if ! wait_for_server $GAME_PORT; then
    echo "Error: Game server failed to start after $MAX_RETRIES retries"
    exit 1
fi

echo "Starting Vite dev server on port $VITE_PORT..."
(cd frontend && bun run dev) &
VITE_PID=$!
sleep 2
if ! kill -0 "$VITE_PID" 2>/dev/null; then
    echo "Error: Vite dev server failed to start"
    exit 1
fi

echo "Starting lobby server on port $LOBBY_PORT..."
echo "Open http://localhost:$LOBBY_PORT in your browser"
uv run uvicorn --factory lobby.server.app:get_app --reload --host 0.0.0.0 --port $LOBBY_PORT
