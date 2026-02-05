#!/bin/bash

# Run game server, client dev server, and lobby server together.
# Ctrl+C stops all servers.

set -e

GAME_PORT=8001
LOBBY_PORT=8000
CLIENT_PORT=3000
MAX_RETRIES=10

kill_tree() {
    local pid="$1"
    # kill children first, then the process itself
    for child in $(pgrep -P "$pid" 2>/dev/null); do
        kill_tree "$child"
    done
    kill "$pid" 2>/dev/null || true
}

cleanup() {
    echo "Stopping servers..."
    if [ -n "$GAME_PID" ]; then
        kill_tree "$GAME_PID"
    fi
    if [ -n "$CLIENT_PID" ]; then
        kill_tree "$CLIENT_PID"
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

echo "Starting client dev server on port $CLIENT_PORT..."
(cd client && bun run dev) &
CLIENT_PID=$!
sleep 2
if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
    echo "Error: Client dev server failed to start"
    exit 1
fi

echo "Starting lobby server on port $LOBBY_PORT..."
echo "Open http://localhost:$CLIENT_PORT in your browser"
uv run uvicorn lobby.server.app:app --reload --host 0.0.0.0 --port $LOBBY_PORT
