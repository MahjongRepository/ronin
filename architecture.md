# Ronin - Architecture Overview

## Services

The system consists of two services in a unified project:

- **Lobby Service** (`src/lobby/`) - Portal for game discovery and creation (port 8000)
- **Game Service** (`src/game/`) - Real-time Mahjong gameplay server (port 8001)


## Game Creation Flow

1. Client calls `POST /games` on lobby (no body required)
2. Lobby selects a healthy game server
3. Lobby generates room ID and calls `POST /rooms` on game server
4. Game server creates empty room
5. Lobby returns WebSocket URL to client
6. Client connects to `ws://game-server/ws/{room_id}`
7. Client sends `join_room` message with player name

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
│   │   └── tests/
│   ├── game/                   # Game server (WebSocket + REST)
│   │   ├── server/
│   │   ├── messaging/
│   │   ├── session/
│   │   ├── logic/
│   │   └── tests/
│   └── shared/                 # Shared code (future use)
```

## Running Locally

Requires [uv](https://docs.astral.sh/uv/) for package management. Dependencies are installed automatically when running commands.

```bash
# Terminal 1: Start game server
make run-game

# Terminal 2: Start lobby
make run-lobby

# Create a game
curl -X POST http://localhost:8000/games

# Response:
# {"room_id": "abc123", "websocket_url": "ws://localhost:8001/ws/abc123", "server_name": "local-1"}
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

1. Implement real Riichi Mahjong game logic in `src/game/logic/`
2. Add game state synchronization
3. Add authentication
4. Add persistence (game history, player stats)
