#!/bin/bash

# Run both game and lobby servers together.
# Game server runs in background, lobby server in foreground.
# Ctrl+C stops both servers.

set -e

GAME_PORT=8001
LOBBY_PORT=8000
MAX_RETRIES=10

cleanup() {
    echo "Stopping servers..."
    if [ -n "$GAME_PID" ]; then
        kill "$GAME_PID" 2>/dev/null || true
    fi
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

trap cleanup EXIT INT TERM

echo "Starting game server on port $GAME_PORT..."
uv run uvicorn game.server.app:app --reload --host 0.0.0.0 --port $GAME_PORT &
GAME_PID=$!

echo "Waiting for game server to be ready..."
if ! wait_for_server $GAME_PORT; then
    echo "Error: Game server failed to start after $MAX_RETRIES retries"
    exit 1
fi

echo "Starting lobby server on port $LOBBY_PORT..."
echo "Open http://localhost:$LOBBY_PORT/static/index.html in your browser"
uv run uvicorn lobby.server.app:app --reload --host 0.0.0.0 --port $LOBBY_PORT
