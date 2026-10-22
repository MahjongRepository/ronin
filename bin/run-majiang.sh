#!/bin/bash
# Запуск ronin (game + lobby) с клиентом Majiang на /play-ng.
#
# Требования:
#   - собранный Majiang:   cd ../Majiang && npm run build  (нужен dist/ronin.html)
#   - собранный lobby-UI:  cd frontend && bun run build    (страницы лобби/комнат;
#     либо поднимите Vite dev на 5173 и поставьте LOBBY_VITE_DEV_URL=http://localhost:5173)
#   - Python >= 3.14 через uv: в PATH или standalone-копия в ../.tools/
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAJIANG_DIST="${MAJIANG_DIST:-$ROOT/../Majiang/dist}"
GAME_PORT=${GAME_PORT:-8711}
LOBBY_PORT=${LOBBY_PORT:-8710}

if command -v uv >/dev/null 2>&1; then
    UV=uv
elif [ -x "$ROOT/../.tools/uv-x86_64-unknown-linux-gnu/uv" ]; then
    UV="$ROOT/../.tools/uv-x86_64-unknown-linux-gnu/uv"
else
    echo "uv не найден. Установите: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/../.tools/uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT/../.tools/python}"

if [ ! -f "$MAJIANG_DIST/ronin.html" ]; then
    echo "Majiang не собран: $MAJIANG_DIST/ronin.html отсутствует" >&2
    echo "Соберите: cd ../Majiang && npm run build" >&2
    exit 1
fi

# Убить остатки прошлых запусков на наших портах
for port in $GAME_PORT $LOBBY_PORT; do
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "[majiang] killing existing processes on port $port..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
done

# Все пути настроек (backend/storage.db, frontend/public, frontend/dist)
# разрешаются относительно корня репозитория — поэтому работаем из $ROOT.
cd "$ROOT"
[ -f .env.local ] && set -a && . ./.env.local && set +a
. bin/local-settings.sh

export LOBBY_GAME_CLIENT_URL="${LOBBY_GAME_CLIENT_URL:-/play-ng}"
export LOBBY_MAJIANG_DIR="$MAJIANG_DIST"
# Origin комнатного/матчмейкинг-WS: страницы открываются с этого же адреса
# (localhost и 127.0.0.1 сервер считает эквивалентными)
export LOBBY_WS_ALLOWED_ORIGIN="${LOBBY_WS_ALLOWED_ORIGIN:-http://localhost:$LOBBY_PORT}"

CONFIG_DIR=$(mktemp -d)
CONFIG_FILE="$CONFIG_DIR/servers.yaml"
cat > "$CONFIG_FILE" <<EOF
servers:
  - name: "local-1"
    url: "http://localhost:$GAME_PORT"
EOF
export LOBBY_CONFIG_PATH="$CONFIG_FILE"

kill_tree() {
    local pid="$1"
    for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
    kill "$pid" 2>/dev/null || true
}

CLEANING_UP=false
cleanup() {
    if $CLEANING_UP; then return; fi
    CLEANING_UP=true
    trap - EXIT INT TERM
    if [ -n "$GAME_PID" ]; then kill_tree "$GAME_PID"; fi
    if [ -n "$LOBBY_PID" ]; then kill_tree "$LOBBY_PID"; fi
    rm -rf "$CONFIG_DIR"
}
trap cleanup EXIT INT TERM

echo "[majiang] game server on :$GAME_PORT"
"$UV" run --project backend uvicorn --factory game.server.app:get_app --host 0.0.0.0 --port "$GAME_PORT" &
GAME_PID=$!

echo "[majiang] lobby server on :$LOBBY_PORT (клиент: /play-ng, ассеты: /majiang)"
"$UV" run --project backend uvicorn --factory lobby.server.app:get_app --host 0.0.0.0 --port "$LOBBY_PORT" &
LOBBY_PID=$!

echo "[majiang] готово: http://localhost:$LOBBY_PORT  (Ctrl+C — остановить)"
wait
