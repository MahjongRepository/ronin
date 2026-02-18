# Lobby Service Architecture

Portal service for room discovery and creation.

**Port**: 8710

## Routes

### Public (no auth required)
- `GET /login` - Login page
- `POST /login` - Validate credentials, set session cookie
- `GET /register` - Registration page
- `POST /register` - Create account, auto-login
- `GET /health` - Health check
- `POST /api/auth/bot` - Exchange bot API key for a game ticket
- `POST /api/rooms/create` - Bot creates a new room and receives a game ticket (authenticates via API key in request body)
- `/static/` - Static files (CSS) served from `frontend/public/`

### Protected (session cookie required)
- `GET /` - Lobby HTML page (fully server-rendered Jinja2 template with zero JavaScript; fetches rooms and renders them inline)
- `POST /rooms/new` - Create a room via HTML form POST, signs a game ticket, then 303 redirect to the game client with `ws_url` and `game_ticket` query params
- `POST /rooms/{room_id}/join` - Join a room, signs a game ticket, then redirects to the game client
- `POST /logout` - Clear session, redirect to login
- `GET /servers` - List available game servers with health status
- `GET /rooms` - List all available rooms across all healthy servers (used by the game client's room.ts)
- `POST /rooms` - Create a new room with optional `num_ai_players` parameter (0-3, defaults to 3)

## Authentication

Ronin uses a three-layer authentication model:

1. **User Accounts** - Username/password registration and login via the lobby web interface. Passwords are hashed with bcrypt.
2. **HMAC-Signed Game Tickets** - The lobby signs HMAC-SHA256 tickets that the game server verifies locally using a shared secret. Tickets contain user identity and room binding.
3. **Bot API Keys** - External bots authenticate via static API keys exchanged for game tickets through `POST /api/auth/bot`.

Human users register and log in through the lobby at `/register` and `/login`. After authentication, creating or joining a room issues a signed game ticket and redirects to the game client. The game server verifies the ticket signature before allowing the WebSocket join.

### Bot Registration

Register a bot account using the CLI tool:

    uv run python bin/register-bot.py <bot_name>

The API key is printed once and never stored. Set `AUTH_USERS_FILE` to control the user store location.

### Running Locally

The `run-local-server.sh` script sets `AUTH_GAME_TICKET_SECRET` automatically and uses `uvicorn --factory` mode to start both servers.

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

- **Server Layer** (`server/`) - Starlette REST API with CORS and auth middleware
- **Settings** (`server/settings.py`) - `LobbyServerSettings` via pydantic-settings (`LOBBY_` env prefix)
- **Auth** (`auth/`) - `AuthMiddleware` for cookie-based session authentication; unprotected paths: `/login`, `/register`, `/health`, `/api/auth/bot`, `/api/rooms/create`; JSON API prefixes (`/rooms`, `/servers`) return 401 instead of redirect when unauthenticated
- **Views** (`views/`) - Jinja2 templates and view handlers for HTML pages and auth forms; `_sign_ticket_and_redirect()` signs HMAC game tickets for room creation/join
- **Registry** (`registry/`) - Game server discovery and health checks
- **Games** (`games/`) - Room listing and creation logic

Dependencies on `shared/`:
- `shared.logging.setup_logging` - Timestamped file and stdout logging
- `shared.validators` - CORS origins parsing and custom env settings source
- `shared.auth` - `AuthService`, `AuthSessionStore`, `FileUserRepository` for user management; `sign_game_ticket` for HMAC-signed game tickets

## Project Structure

```
ronin/
└── backend/
    └── lobby/
        ├── server/
        │   ├── app.py          # Starlette app factory and route handlers
        │   └── settings.py     # LobbyServerSettings (pydantic-settings)
        ├── auth/
        │   └── middleware.py    # AuthMiddleware (cookie-based session auth)
        ├── views/
        │   ├── handlers.py     # View handlers (lobby_page, room creation/join with ticket signing)
        │   ├── auth_handlers.py # Auth handlers (login, register, logout, bot_auth)
        │   └── templates/
        │       ├── base.html   # Base template with CSS link
        │       ├── lobby.html  # Lobby page template
        │       ├── login.html  # Login form template
        │       └── register.html # Registration form template
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

### API Flow (POST /rooms)
1. Client calls `POST /rooms` with optional `{"num_ai_players": N}` (defaults to 3)
2. Lobby checks health of all configured game servers (sequentially, not concurrent)
3. Lobby selects the first healthy server (no load balancing)
4. Lobby generates a UUID4 room ID
5. Lobby calls `POST /rooms` on the game server with `{"room_id": ..., "num_ai_players": ...}`
6. Lobby constructs WebSocket URL by replacing `http://` with `ws://` (or `https://` with `wss://`) and appending `/ws/{room_id}`
7. Lobby returns WebSocket URL to client

### Browser Flow (POST /rooms/new, POST /rooms/{room_id}/join)
1. Authenticated user submits an HTML form
2. Lobby creates the room on a game server (or validates the room exists for join)
3. Lobby signs a 24-hour HMAC-SHA256 game ticket containing `user_id`, `username`, `room_id`, `issued_at`, `expires_at` using the `AUTH_GAME_TICKET_SECRET`. The game ticket doubles as the session identifier for the entire game lifecycle, including reconnection
4. Lobby redirects (303) to the game client URL with `ws_url` and `game_ticket` query params
5. The game client connects to the WebSocket and sends the signed ticket in the `join_room` message
6. The game server verifies the ticket signature and expiry before allowing the join

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

Lobby settings (prefixed with `LOBBY_`):

- `LOBBY_CONFIG_PATH` - Override default servers.yaml file path (default: `backend/config/servers.yaml`)
- `LOBBY_LOG_DIR` - Log file directory (default: `backend/logs/lobby`)
- `LOBBY_CORS_ORIGINS` - Allowed CORS origins as JSON array or CSV string (default: `["http://localhost:8712"]`)
- `LOBBY_STATIC_DIR` - Static files directory for CSS (default: `frontend/public`)
- `LOBBY_GAME_CLIENT_URL` - Game client URL for room creation redirects and join links (default: `http://localhost:8712`)

Auth settings (prefixed with `AUTH_`):

- `AUTH_GAME_TICKET_SECRET` - HMAC-SHA256 secret for signing/verifying game tickets (shared between lobby and game server)
- `AUTH_USERS_FILE` - Path to the file-backed user repository
- `AUTH_COOKIE_SECURE` - Set cookie Secure flag (default: `false`, set `true` in production for HTTPS)
