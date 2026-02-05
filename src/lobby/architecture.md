# Lobby Service Architecture

Portal service for game discovery and creation.

**Port**: 8000

## REST API

- `GET /health` - Health check
- `GET /servers` - List available game servers with health status
- `GET /games` - List all available games across all healthy servers
- `POST /games` - Create a new game with optional `num_bots` parameter (0-3, defaults to 3)

### List Games Response

```json
{
  "games": [
    {
      "game_id": "abc123",
      "player_count": 2,
      "max_players": 4,
      "num_bots": 1,
      "server_name": "local-1",
      "server_url": "http://localhost:8001"
    }
  ]
}
```

### Create Game Request/Response

```json
// Request (POST /games):
{"num_bots": 1}

// Response (201):
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
        │   ├── types.py        # CreateGameRequest, CreateGameResponse
        │   └── service.py      # GamesService
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-all-checks       # Run all checks
```

## Game Creation Flow

1. Client calls `POST /games` with optional `{"num_bots": N}` (defaults to 3)
2. Lobby checks health of all configured game servers
3. Lobby selects a healthy server (first available)
4. Lobby generates a game ID
5. Lobby calls `POST /games` on the game server with `num_bots`
6. Lobby returns WebSocket URL to client

## Game Listing Flow

1. Client calls `GET /games`
2. Lobby checks health of all configured game servers
3. Lobby calls `GET /games` on each healthy server
4. Lobby aggregates results with server info (including `num_bots` per game)
5. Lobby returns combined list to client

## Environment Variables

- `LOBBY_CONFIG_PATH` - Override default config file path
