# Lobby Service Architecture

Portal service for game discovery and creation.

**Port**: 8000

## REST API

- `GET /` - Redirect to `/static/index.html`
- `GET /health` - Health check
- `GET /servers` - List available game servers with health status
- `GET /games` - List all available games across all healthy servers
- `POST /games` - Create a new game
- `GET /static/*` - Static file serving

### List Games Response

```json
{
  "games": [
    {
      "game_id": "abc123",
      "player_count": 2,
      "max_players": 4,
      "server_name": "local-1",
      "server_url": "http://localhost:8001"
    }
  ]
}
```

### Create Game Response

```json
{
  "game_id": "abc123",
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
- **Games** (`games/`) - Game listing and creation logic

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
        ├── static/
        │   └── index.html      # Games list and creation UI
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-all           # Run game, client, and lobby servers
make run-lobby         # Start server on port 8000
make run-client        # Start client dev server on port 3000
make test-lobby        # Run lobby tests
make lint              # Run linter
make format            # Format code
make typecheck         # Run Python type checking (ty)
make typecheck-client  # Run TypeScript type checking
make check-agent       # Run all checks
```

## Game Creation Flow

1. Client calls `POST /games`
2. Lobby checks health of all configured game servers
3. Lobby selects a healthy server (first available)
4. Lobby generates a game ID
5. Lobby calls `POST /games` on the game server
6. Lobby returns WebSocket URL to client

## Game Listing Flow

1. Client calls `GET /games`
2. Lobby checks health of all configured game servers
3. Lobby calls `GET /games` on each healthy server
4. Lobby aggregates results with server info
5. Lobby returns combined list to client

## Environment Variables

- `LOBBY_CONFIG_PATH` - Override default config file path
