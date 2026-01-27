# Lobby Service Architecture

Portal service for game discovery and creation.

**Port**: 8000

## REST API

- `GET /health` - Health check
- `GET /servers` - List available game servers with health status
- `POST /games` - Create a new game

### Create Game Response

```json
{
  "room_id": "abc123",
  "websocket_url": "ws://localhost:8001/ws/abc123",
  "server_name": "local-1"
}
```

## Configuration

### Game Server Registry

`src/config/servers.yaml`:

```yaml
servers:
  - name: "local-1"
    url: "http://localhost:8001"
```

The lobby periodically checks server health via `GET /health` and only routes games to healthy servers.

## Internal Architecture

- **Server Layer** (`server/`) - Starlette REST API
- **Registry** (`registry/`) - Game server discovery and health checks
- **Games** (`games/`) - Game creation logic

## Project Structure

```
ronin/
├── pyproject.toml
├── Makefile
├── config/
│   └── servers.yaml        # Game server registry
└── src/
    └── lobby/
        ├── server/
        │   └── app.py          # Starlette app
        ├── registry/
        │   ├── types.py        # GameServer, ServerStatus
        │   └── manager.py      # RegistryManager
        ├── games/
        │   ├── types.py        # CreateGameResponse
        │   └── service.py      # GamesService
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-lobby   # Start server on port 8000
make test-lobby  # Run lobby tests
make lint        # Run linter
make format      # Format code
```

## Game Creation Flow

1. Client calls `POST /games`
2. Lobby checks health of all configured game servers
3. Lobby selects a healthy server (first available)
4. Lobby generates a room ID
5. Lobby calls `POST /rooms` on the game server
6. Lobby returns WebSocket URL to client

## Environment Variables

- `LOBBY_CONFIG_PATH` - Override default config file path
