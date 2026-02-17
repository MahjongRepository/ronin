#!/bin/bash
set -e

# Build lobby CSS and game CSS before starting watchers
bun run sass:lobby
bun run sass:game

# Start watchers and dev server; clean up all children on exit
cleanup() {
    kill 0 2>/dev/null
}
trap cleanup EXIT INT TERM

bunx sass --watch src/styles/lobby-app.scss:public/styles/lobby.css --no-source-map &
bunx sass --watch src/styles/game-app.scss:public/styles/game.css --no-source-map &
bun ./index.html --port "${PORT:-8712}"
