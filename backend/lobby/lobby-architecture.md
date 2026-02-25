# Lobby Service Architecture

Portal service for room management, authentication, and game client serving.

**Port**: 8710

## Routes

### Public (no auth required)
- `GET /login` - Login page
- `POST /login` - Validate credentials, set session cookie
- `GET /register` - Registration page
- `POST /register` - Create account, auto-login
- `GET /health` - Health check
- `POST /logout` - Clear session, redirect to login
- `/static/` - Static files (CSS) served from `frontend/public/`
- `/game-assets/` - Built game client assets (content-hashed JS/CSS) served from `frontend/dist/`

### Protected (session cookie or API key required)
- `GET /` - Lobby HTML page (server-rendered, lists rooms from local room manager)
- `GET /game` - Game client HTML page (Jinja2 template serving the built frontend with content-hashed JS/CSS)
- `POST /rooms/new` - Create a local room, 303 redirect to `/rooms/{room_id}`
- `GET /rooms/{room_id}` - Room page (Jinja2 template with embedded TypeScript for room UI)
- `POST /rooms/{room_id}/join` - Validate room exists, redirect to `/rooms/{room_id}`
- `GET /servers` - List available game servers with health status
- `POST /api/auth/bot` - Create a lobby session for an authenticated bot to join a room via WebSocket
- `POST /api/rooms` - Create a room (bot API); returns `room_id`, `session_id`, and `ws_url`

### WebSocket (auth handled inside the handler)
- `WS /ws/rooms/{room_id}` - Room WebSocket (JSON protocol, session cookie auth, origin check)

## Authentication

Ronin uses a three-layer authentication model:

1. **Player Accounts** - Username/password registration and login via the lobby web interface. Passwords are hashed with bcrypt.
2. **HMAC-Signed Game Tickets** - The lobby signs HMAC-SHA256 tickets that the game server verifies locally using a shared secret. Tickets contain player identity and room binding.
3. **Bot API Keys** - External bots authenticate via `X-API-Key` header on protected API routes (`POST /api/auth/bot`, `POST /api/rooms`). The lobby validates the key and returns a lobby session for WebSocket access.

Human users register and log in through the lobby at `/register` and `/login`. After authentication, creating or joining a room redirects to the room page (`/rooms/{room_id}`). Game tickets are signed when all players ready up and the game transitions to the game server. The `SessionOrApiKeyBackend` checks session cookies first, then the `session_id` query parameter (used by WebSocket clients), then falls back to `X-API-Key` header for bot accounts.

### Bot Registration

Register a bot account using the CLI tool:

    uv run python bin/register-bot.py <bot_name>

The API key is printed once and never stored. Set `AUTH_DATABASE_PATH` to control the SQLite database location (default: `backend/storage.db`).

### Running Locally

The `run-local-server.sh` script sets `AUTH_GAME_TICKET_SECRET` automatically and uses `uvicorn --factory` mode to start both servers.

### Room WebSocket Protocol

The lobby room WebSocket uses JSON text frames. Client-to-server messages:
- `{"type": "set_ready", "ready": true}` - Toggle ready state
- `{"type": "chat", "text": "Hello!"}` - Send chat message
- `{"type": "leave_room"}` - Leave the room
- `{"type": "ping"}` - Heartbeat keep-alive

Server-to-client messages:
- `{"type": "room_joined", "room_id": "...", "player_name": "...", "players": [...], "num_ai_players": N}` - Sent on join
- `{"type": "player_joined", "player_name": "...", "players": [...]}` - Player joined broadcast
- `{"type": "player_left", "player_name": "...", "players": [...]}` - Player left broadcast
- `{"type": "player_ready_changed", "player_name": "...", "ready": true, "players": [...]}` - Ready state broadcast
- `{"type": "chat", "player_name": "...", "text": "..."}` - Chat broadcast
- `{"type": "game_starting", "ws_url": "...", "game_ticket": "...", "game_id": "...", "game_client_url": "/game"}` - Game transition
- `{"type": "error", "message": "..."}` - Error message
- `{"type": "pong"}` - Heartbeat response

## Configuration

### Game Server Registry

`backend/config/servers.yaml`:

```yaml
servers:
  - name: "local-1"
    url: "http://localhost:8711"
```

The lobby checks server health via `GET /health` on every incoming request that touches servers (`GET /servers`, game transitions). There is no background polling or caching — each request triggers a fresh health check of all configured servers.

### CORS

CORS middleware is configured with origins from `LOBBY_CORS_ORIGINS`, allowing all methods and headers.

## Game Client Serving

The backend serves the game client directly via a Jinja2 template at `/game`, eliminating the need for a separate static file server. Content-hashed frontend assets (JS, CSS) are served from `/game-assets/`.

### Asset Discovery

The frontend build (`bun run build:game`) produces content-hashed files (e.g., `index-hqf7q5nj.js`) in `frontend/dist/`. A post-build script (`frontend/scripts/generate-manifest.ts`) scans the output and writes `dist/manifest.json`:

```json
{"js": "index-hqf7q5nj.js", "css": "game-app-k3m9x2.css"}
```

At startup, the backend reads this manifest and passes the filenames to the `game.html` Jinja2 template, which renders the correct `<script>` and `<link>` tags.

### CSP Policy

The security headers middleware applies route-aware Content Security Policy:
- **Lobby/auth pages** — `script-src 'none'` (no JavaScript)
- **Room pages** (`/rooms/`) — `script-src 'self'` and `connect-src 'self'` (allows scripts and same-origin WebSocket connections)
- **Game pages** (`/game`, `/game-assets/`) — `script-src 'self'` and `connect-src 'self' ws: wss:` (allows scripts and cross-origin WebSocket connections to game servers)

### Dev Mode

`run-local-server.sh` sets `LOBBY_GAME_CLIENT_URL=http://localhost:$CLIENT_PORT`, which overrides the `/game` default. The Bun dev server continues to serve the game client separately for hot reloading during development.

## Internal Architecture

- **Server Layer** (`server/`) - Starlette REST API with CORS and auth middleware
- **Settings** (`server/settings.py`) - `LobbyServerSettings` via pydantic-settings (`LOBBY_` env prefix)
- **Auth** (`auth/`) - Starlette `AuthenticationMiddleware` with `SessionOrApiKeyBackend` for cookie/query-param session or `X-API-Key` header authentication; route authorization via `protected_html`, `protected_api`, and `public_route` policy decorators with startup validation (fail-closed); JSON API routes (`/servers`, `/api/*`) return 401 instead of redirect when unauthenticated
- **Views** (`views/`) - Jinja2 templates and view handlers for HTML pages and auth forms; `create_signed_ticket()` signs HMAC game tickets at game-start time; `game_page` serves the built frontend via `game.html` template with manifest-driven asset URLs; `room_page` serves the room UI via `room.html` template
- **Registry** (`registry/`) - Game server discovery and health checks
- **Rooms** (`rooms/`) - Room management: `LobbyRoomManager` (room state, TTL reaper), `RoomConnectionManager` (WebSocket broadcasting), WebSocket handler (auth, origin check, game transition), typed message models, room data models

Dependencies on `shared/`:
- `shared.logging.setup_logging` - Timestamped file and stdout logging
- `shared.validators` - CORS origins parsing and custom env settings source
- `shared.auth` - `AuthService`, `AuthSessionStore`, `PlayerRepository` for player management; `sign_game_ticket` for HMAC-signed game tickets
- `shared.db` - `Database`, `SqlitePlayerRepository` for SQLite-backed player storage

## Project Structure

```
ronin/
└── backend/
    └── lobby/
        ├── server/
        │   ├── app.py          # Starlette app factory and route handlers
        │   ├── middleware.py   # SecurityHeadersMiddleware (route-aware CSP), SlashNormalizationMiddleware
        │   └── settings.py     # LobbyServerSettings (pydantic-settings)
        ├── auth/
        │   ├── backend.py      # SessionOrApiKeyBackend (Starlette AuthenticationBackend)
        │   ├── models.py       # AuthenticatedPlayer (Starlette BaseUser)
        │   └── policy.py       # Route auth policy decorators and startup validation
        ├── views/
        │   ├── handlers.py     # View handlers (lobby_page, room_page, game_page, room creation/join)
        │   ├── auth_handlers.py # Auth handlers (login, register, logout, bot_auth, bot_create_room)
        │   └── templates/
        │       ├── base.html   # Base template with CSS block and scripts block
        │       ├── lobby.html  # Lobby page template
        │       ├── room.html   # Room page template (WebSocket-based room UI)
        │       ├── game.html   # Game client template (manifest-driven asset URLs)
        │       ├── login.html  # Login form template
        │       └── register.html # Registration form template
        ├── registry/
        │   ├── types.py        # GameServer model
        │   └── manager.py      # RegistryManager
        ├── rooms/
        │   ├── __init__.py
        │   ├── connections.py  # RoomConnectionManager (WebSocket broadcasting)
        │   ├── manager.py      # LobbyRoomManager (room state, TTL reaper)
        │   ├── messages.py     # Typed client->server lobby message models
        │   ├── models.py       # LobbyRoom, LobbyPlayer, LobbyPlayerInfo
        │   └── websocket.py    # Room WebSocket handler (auth, origin check, game transition)
        └── tests/
            ├── unit/
            └── integration/
```

## Room Creation Flow

### Browser Flow (POST /rooms/new)
1. Authenticated user submits the HTML form
2. Lobby generates a UUID room_id
3. Lobby creates the room locally via `room_manager.create_room(room_id)`
4. Lobby redirects (303) to `/rooms/{room_id}`
5. Room page loads and connects to lobby WebSocket at `/ws/rooms/{room_id}`
6. Server auto-joins the player to the room

### Game Transition Flow (all players ready)
1. All players set ready via WebSocket
2. Lobby signs HMAC game tickets for each player
3. Lobby calls `POST /games` on a game server with player specs
4. On success, lobby sends `game_starting` to each player with their ticket and WS URL
5. Players navigate to game client and connect via `JOIN_GAME`

## Room Listing Flow

1. Client requests `GET /`
2. Lobby calls `room_manager.get_rooms_info()` (local, no HTTP calls)
3. Lobby renders the room list in the Jinja2 template

## Key Implementation Details

- **Application state injection**: Services (`RegistryManager`, `LobbyRoomManager`, `RoomConnectionManager`, `LobbyServerSettings`) are stored on `app.state` at creation time and accessed in handlers via `request.app.state`.
- **Module-level instantiation**: Importing `lobby.server.app` triggers settings creation, logging setup, and app creation. The `create_app()` factory exists for testing with custom settings.
- **Room data is strongly typed**: Room state is managed via `LobbyRoom` dataclass and `LobbyPlayerInfo` Pydantic model.

## Environment Variables

Lobby settings (prefixed with `LOBBY_`):

- `LOBBY_CONFIG_PATH` - Override default servers.yaml file path (default: `backend/config/servers.yaml`)
- `LOBBY_LOG_DIR` - Log file directory (default: `backend/logs/lobby`)
- `LOBBY_CORS_ORIGINS` - Allowed CORS origins as JSON array or CSV string (default: `["http://localhost:8712"]`)
- `LOBBY_STATIC_DIR` - Static files directory for CSS (default: `frontend/public`)
- `LOBBY_GAME_CLIENT_URL` - Game client URL for room creation redirects and join links (default: `/game`)
- `LOBBY_WS_ALLOWED_ORIGIN` - Allowed origin for WebSocket connections (CSRF protection). Default: `http://localhost:8710`. Set to `None` to allow all origins
- `LOBBY_GAME_ASSETS_DIR` - Directory containing built game client assets and `manifest.json` (default: `frontend/dist`)

Auth settings (prefixed with `AUTH_`):

- `AUTH_GAME_TICKET_SECRET` - HMAC-SHA256 secret for signing/verifying game tickets (shared between lobby and game server)
- `AUTH_DATABASE_PATH` - Path to the SQLite database file (default: `backend/storage.db`)
- `AUTH_COOKIE_SECURE` - Set cookie Secure flag (default: `false`, set `true` in production for HTTPS)
