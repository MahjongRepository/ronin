# Lobby Service Architecture

Portal service for room discovery and creation.

**Port**: 8000

## REST API

- `GET /health` - Health check
- `GET /servers` - List available game servers with health status
- `GET /rooms` - List all available rooms across all healthy servers
- `POST /rooms` - Create a new room with optional `num_bots` parameter (0-3, defaults to 3)

### List Rooms Response

```json
{
  "rooms": [
    {
      "room_id": "abc123",
      "human_player_count": 2,
      "humans_needed": 3,
      "total_seats": 4,
      "num_bots": 1,
      "players": ["Alice", "Bob"],
      "server_name": "local-1",
      "server_url": "http://localhost:8001"
    }
  ]
}
```

### Create Room Request/Response

```json
// Request (POST /rooms):
{"num_bots": 1}

// Response (201):
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

The lobby periodically checks server health via `GET /health` and only routes rooms to healthy servers.

## Internal Architecture

- **Server Layer** (`server/`) - Starlette REST API
- **Registry** (`registry/`) - Game server discovery and health checks
- **Games** (`games/`) - Room listing and creation logic

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
        │   ├── types.py        # CreateRoomRequest, CreateRoomResponse
        │   └── service.py      # GamesService
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-all-checks       # Run all checks
```

## Room Creation Flow

1. Client calls `POST /rooms` with optional `{"num_bots": N}` (defaults to 3)
2. Lobby checks health of all configured game servers
3. Lobby selects a healthy server (first available)
4. Lobby generates a room ID
5. Lobby calls `POST /rooms` on the game server with `num_bots`
6. Lobby returns WebSocket URL to client

## Room Listing Flow

1. Client calls `GET /rooms`
2. Lobby checks health of all configured game servers
3. Lobby calls `GET /rooms` on each healthy server
4. Lobby aggregates results with server info (including `num_bots` per room)
5. Lobby returns combined list to client

## Environment Variables

- `LOBBY_CONFIG_PATH` - Override default config file path
