# Ronin - Architecture Overview

## Services

The system consists of two services in a unified project:

- **Lobby Service** (`src/lobby/`) - Portal for game discovery and creation (port 8000)
- **Game Service** (`src/game/`) - Real-time Riichi Mahjong gameplay server with full game logic (port 8001)

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
5. Lobby page redirects to game page with URL parameters: `http://localhost:8001/static/game.html?game_id=xxx&websocket_url=ws://...&player_name=Player_xxx`
6. Game page reads parameters and auto-connects with the provided player name
7. Game page establishes WebSocket connection and sends `join_game` message

## Web UI

Both services include static HTML pages for browser-based interaction:

- **Lobby Page** (`/static/index.html` on port 8000) - Displays available games with "Join" buttons and a "Create Game" button. Player names are auto-generated.
- **Game Page** (`/static/game.html` on port 8001) - WebSocket-based game interface with real-time connection status

The HTML pages use vanilla JavaScript with no external dependencies. They communicate with the backend using the existing REST and WebSocket APIs.

## Project Structure

```
ronin/
├── pyproject.toml              # Unified project config
├── Makefile                    # Build targets for both services
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
│   │   ├── static/             # Game HTML pages
│   │   └── tests/
│   └── shared/                 # Shared code (future use)
```

## Running Locally

Requires [uv](https://docs.astral.sh/uv/) for package management. Dependencies are installed automatically when running commands.

```bash
# Run both servers together (recommended for local testing)
make run-all

# Or run servers separately:
# Terminal 1: Start game server
make run-game

# Terminal 2: Start lobby
make run-lobby
```

Using the Web UI:
1. Run `make run-all` to start both servers
2. Open http://localhost:8000/static/index.html in your browser
3. Click "Create Game" to create a new game, or "Join" an existing one
4. You'll be automatically connected with a generated player name

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
make test          # Run all tests
make test-lobby    # Run lobby tests only
make test-game     # Run game tests only
make lint          # Check code style
make format        # Auto-format code
```

## Next Steps

1. Add game state synchronization
2. Add authentication
3. Add persistence (game history, player stats)
