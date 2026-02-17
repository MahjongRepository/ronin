# Lobby Service Architecture

Portal service for room discovery and creation.

**Port**: 8710

## Routes

- `GET /` - Lobby HTML page (fully server-rendered Jinja2 template with zero JavaScript; fetches rooms and renders them inline)
- `POST /rooms/new` - Create a room via HTML form POST, then 303 redirect to the game client with `ws_url` and `player_name` query params
- `GET /health` - Health check
- `GET /servers` - List available game servers with health status
- `GET /rooms` - List all available rooms across all healthy servers (used by the game client's room.ts)
- `POST /rooms` - Create a new room with optional `num_ai_players` parameter (0-3, defaults to 3)
- `/static/` - Static files (CSS) served from `frontend/public/`

### List Rooms Response

The lobby passes through room data from game servers as-is (fields like `room_id`, `player_count`, `players_needed`, `total_seats`, `num_ai_players`, `players` come from the game server and are not validated by the lobby). The lobby injects `server_name` and `server_url` into each room entry.

```json
{
  "rooms": [
    {
      "room_id": "abc123",
      "player_count": 2,
      "players_needed": 3,
      "total_seats": 4,
      "num_ai_players": 1,
      "players": ["Alice", "Bob"],
      "server_name": "local-1",
      "server_url": "http://localhost:8711"
    }
  ]
}
```

### Create Room Request/Response

```json
// Request (POST /rooms):
{"num_ai_players": 1}

// Response (201):
{
  "room_id": "abc123",
  "websocket_url": "ws://localhost:8711/ws/abc123",
  "server_name": "local-1"
}
```

### Error Responses

- **422** - Invalid `num_ai_players` value (outside 0-3 range or wrong type). Returns Pydantic validation error details.
- **503** - No healthy game servers available, or game server failed to create the room. Returns `{"error": "..."}`.

## Configuration

### Game Server Registry

`backend/config/servers.yaml`:

```yaml
servers:
  - name: "local-1"
    url: "http://localhost:8711"
```

The lobby checks server health via `GET /health` on every incoming request that touches servers (`GET /servers`, `GET /rooms`, `POST /rooms`). There is no background polling or caching — each request triggers a fresh health check of all configured servers.

### CORS

CORS middleware is configured with origins from `LOBBY_CORS_ORIGINS`, allowing all methods and headers.

## Internal Architecture

- **Server Layer** (`server/`) - Starlette REST API with CORS middleware
- **Settings** (`server/settings.py`) - `LobbyServerSettings` via pydantic-settings (`LOBBY_` env prefix)
- **Views** (`views/`) - Jinja2 templates and view handlers for HTML pages
- **Registry** (`registry/`) - Game server discovery and health checks
- **Games** (`games/`) - Room listing and creation logic

Dependencies on `shared/`:
- `shared.logging.setup_logging` - Timestamped file and stdout logging
- `shared.validators` - CORS origins parsing and custom env settings source

## Project Structure

```
ronin/
└── backend/
    └── lobby/
        ├── server/
        │   ├── app.py          # Starlette app factory and route handlers
        │   └── settings.py     # LobbyServerSettings (pydantic-settings)
        ├── views/
        │   ├── handlers.py     # View handlers (lobby_page)
        │   └── templates/
        │       ├── base.html   # Base template with CSS link
        │       └── lobby.html  # Lobby page template
        ├── registry/
        │   ├── types.py        # GameServer model
        │   └── manager.py      # RegistryManager
        ├── games/
        │   ├── types.py        # CreateRoomRequest, CreateRoomResponse
        │   └── service.py      # GamesService, RoomCreationError
        └── tests/
            ├── unit/
            └── integration/
```

## Room Creation Flow

1. Client calls `POST /rooms` with optional `{"num_ai_players": N}` (defaults to 3)
2. Lobby checks health of all configured game servers (sequentially, not concurrent)
3. Lobby selects the first healthy server (no load balancing)
4. Lobby generates a UUID4 room ID
5. Lobby calls `POST /rooms` on the game server with `{"room_id": ..., "num_ai_players": ...}`
6. Lobby constructs WebSocket URL by replacing `http://` with `ws://` (or `https://` with `wss://`) and appending `/ws/{room_id}`
7. Lobby returns WebSocket URL to client

## Room Listing Flow

1. Client calls `GET /rooms`
2. Lobby checks health of all configured game servers
3. Lobby calls `GET /rooms` on each healthy server (sequentially)
4. Lobby aggregates results, injecting `server_name` and `server_url` into each room
5. If a healthy server fails to respond or returns invalid JSON, that server is silently skipped
6. Lobby returns combined list to client

## Key Implementation Details

- **Application state injection**: Services (`RegistryManager`, `GamesService`, `LobbyServerSettings`) are stored on `app.state` at creation time and accessed in handlers via `request.app.state`.
- **Module-level instantiation**: Importing `lobby.server.app` triggers settings creation, logging setup, and app creation. The `create_app()` factory exists for testing with custom settings.
- **Room data is untyped**: `list_rooms()` returns `list[dict[str, Any]]` — room data from game servers passes through without Pydantic validation.

## Environment Variables

All prefixed with `LOBBY_`:

- `LOBBY_CONFIG_PATH` - Override default servers.yaml file path (default: `backend/config/servers.yaml`)
- `LOBBY_LOG_DIR` - Log file directory (default: `backend/logs/lobby`)
- `LOBBY_CORS_ORIGINS` - Allowed CORS origins as JSON array or CSV string (default: `["http://localhost:8712"]`)
- `LOBBY_STATIC_DIR` - Static files directory for CSS (default: `frontend/public`)
- `LOBBY_GAME_CLIENT_URL` - Game client URL for room creation redirects and join links (default: `http://localhost:8712`)
