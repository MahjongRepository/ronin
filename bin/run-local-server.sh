#!/bin/bash

# Run game server, client dev server, and lobby server together.
# Ctrl+C stops all servers.

set -e

GAME_PORT=${GAME_PORT:-8711}
LOBBY_PORT=${LOBBY_PORT:-8710}
CLIENT_PORT=${CLIENT_PORT:-8712}
MAX_RETRIES=10

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

# Set CORS origins so game and lobby servers accept requests from the client port
export GAME_CORS_ORIGINS="http://localhost:$CLIENT_PORT"
export LOBBY_CORS_ORIGINS="http://localhost:$CLIENT_PORT"

# Generate client env config with lobby URL
mkdir -p frontend/public
cat > frontend/public/env.js <<EOF
window.__LOBBY_URL__ = "http://localhost:$LOBBY_PORT";
EOF

# Build lobby CSS for server-side templates
(cd frontend && bun run sass:lobby)

# Set lobby settings for template rendering
export LOBBY_GAME_CLIENT_URL="http://localhost:$CLIENT_PORT"

cleanup() {
    echo "Stopping servers..."
    if [ -n "$GAME_PID" ]; then
        kill_tree "$GAME_PID"
    fi
    if [ -n "$CLIENT_PID" ]; then
        kill_tree "$CLIENT_PID"
    fi
    rm -rf "$CONFIG_DIR"
}

trap cleanup EXIT INT TERM

echo "Starting game server on port $GAME_PORT..."
uv run uvicorn --factory game.server.app:get_app --reload --host 0.0.0.0 --port $GAME_PORT &
GAME_PID=$!

echo "Waiting for game server to be ready..."
if ! wait_for_server $GAME_PORT; then
    echo "Error: Game server failed to start after $MAX_RETRIES retries"
    exit 1
fi

echo "Starting client dev server on port $CLIENT_PORT..."
(cd frontend && PORT=$CLIENT_PORT bun run dev) &
CLIENT_PID=$!
sleep 2
if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
    echo "Error: Client dev server failed to start"
    exit 1
fi

echo "Starting lobby server on port $LOBBY_PORT..."
echo "Open http://localhost:$LOBBY_PORT in your browser"
uv run uvicorn --factory lobby.server.app:get_app --reload --host 0.0.0.0 --port $LOBBY_PORT
