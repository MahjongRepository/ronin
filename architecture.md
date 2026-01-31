# Ronin - Architecture Overview

## Services

The system consists of two backend services and a TypeScript client in a unified project:

- **Lobby Service** (`src/lobby/`) - Portal for game discovery and creation (port 8000)
- **Game Service** (`src/game/`) - Real-time Riichi Mahjong gameplay server with full game logic (port 8001)
- **Client** (`client/`) - TypeScript + SASS frontend using Bun dev server (port 3000)

## Game Creation Flow

API flow:
1. Client calls `POST /games` on lobby (no body required)
2. Lobby selects a healthy game server
3. Lobby generates game ID and calls `POST /games` on game server
4. Game server creates empty game
5. Lobby returns WebSocket URL to client
6. Client connects to `ws://game-server/ws/{game_id}`
7. Client sends `join_game` message with player name

Web UI flow:
1. User opens lobby page at `http://localhost:8000/static/index.html`
2. Lobby page displays list of available games (fetched via `GET /games`)
3. User clicks "Create Game" to create a new game, or "Join" on an existing game
4. Lobby page calls `POST /games` (for create) and receives game_id and websocket_url
5. Lobby page redirects to legacy game page with URL parameters: `http://localhost:8001/static/game.legacy.html?game_id=xxx&websocket_url=ws://...&player_name=Player_xxx`
6. Game page reads parameters and auto-connects with the provided player name
7. Game page establishes WebSocket connection and sends `join_game` message

## Web UI

- **Client** (`client/`, port 3000) - TypeScript + SASS application served by Bun's dev server. Entry point is `client/index.html` with TypeScript transpiled on-the-fly by Bun and SASS compiled via the `sass` CLI.
- **Lobby Page** (`/static/index.html` on port 8000) - Displays available games with "Join" buttons and a "Create Game" button. Player names are auto-generated.
- **Legacy Game Page** (`/static/game.legacy.html` on port 8001) - Archived vanilla JS game interface, kept for reference.

## Project Structure

```
ronin/
├── pyproject.toml              # Unified project config
├── Makefile                    # Build targets for all services
├── client/                     # TypeScript + SASS frontend (Bun)
│   ├── index.html              # HTML entry point
│   ├── package.json            # Bun project config
│   ├── tsconfig.json           # TypeScript configuration
│   └── src/
│       ├── index.ts            # Application entry point
│       └── styles/
│           └── main.scss       # SASS styles
├── src/
│   ├── config/
│   │   └── servers.yaml        # Game server registry
│   ├── lobby/                  # Portal service (REST API)
│   │   ├── server/
│   │   ├── registry/
│   │   ├── games/
│   │   ├── static/             # Lobby HTML pages
│   │   └── tests/
│   ├── game/                   # Game server (WebSocket + REST)
│   │   ├── server/
│   │   ├── messaging/
│   │   ├── session/
│   │   ├── logic/              # Riichi Mahjong rules implementation
│   │   ├── static/             # Legacy game HTML pages
│   │   └── tests/
│   └── shared/                 # Shared code (future use)
```

## Running Locally

Requires [uv](https://docs.astral.sh/uv/) for Python package management and [Bun](https://bun.sh/) for the TypeScript client. Dependencies are installed automatically when running commands.

```bash
# Run all servers together (recommended for local testing)
make run-all

# Or run servers separately:
make run-game      # Game server on port 8001
make run-lobby     # Lobby server on port 8000
make run-client    # Client dev server on port 3000
```

Using the Web UI:
1. Run `make run-all` to start all servers
2. Open http://localhost:3000 in your browser for the game client
3. Open http://localhost:8000/static/index.html for the lobby page

Using the API directly:
```bash
# List available games
curl http://localhost:8000/games

# Create a game
curl -X POST http://localhost:8000/games

# Response:
# {"game_id": "abc123", "websocket_url": "ws://localhost:8001/ws/abc123", "server_name": "local-1"}
```

## Development

```bash
make test              # Run all tests
make test-lobby        # Run lobby tests only
make test-game         # Run game tests only
make lint              # Check code style
make format            # Auto-format code
make typecheck         # Run Python type checking (ty)
make typecheck-client  # Run TypeScript type checking
make check-agent       # Run all checks (format, lint, typecheck, test, client typecheck)
```

## Next Steps

1. Add game state synchronization
2. Add authentication
3. Add persistence (game history, player stats)
