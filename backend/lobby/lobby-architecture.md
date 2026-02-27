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
- `/static/` - Static files (CSS, JS) served from `frontend/public/`
- `/game-assets/` - Built game client assets (content-hashed JS/CSS) served from `frontend/dist/`

### Protected (session cookie or API key required)
- `GET /` - Lobby HTML page (server-rendered, lists rooms from local room manager)
- `GET /history` - History page (server-rendered, shows 20 most recent played games with player names, scores, and winner info)
- `GET /play/{game_id}` - Game client HTML page (Jinja2 template serving the built frontend with content-hashed JS/CSS)
- `POST /rooms/new` - Create a local room, 303 redirect to `/rooms/{room_id}`
- `GET /rooms/{room_id}` - Room page (Jinja2 template with embedded TypeScript for room UI)
- `POST /rooms/{room_id}/join` - Validate room exists, redirect to `/rooms/{room_id}`
- `GET /servers` - List available game servers with health status

### Bot-Only (bot account required)
- `POST /api/auth/bot` - Create a lobby session for an authenticated bot to join a room via WebSocket (403 for human accounts)
- `POST /api/rooms` - Create a room (bot API); accepts optional `min_human_players` (integer 1-4, default 1) to require multiple humans before game start; returns `room_id`, `session_id`, and `ws_url` (403 for human accounts)

### WebSocket (auth handled inside the handler)
- `WS /ws/rooms/{room_id}` - Room WebSocket (JSON protocol, session cookie auth, origin check)

## Authentication

Ronin uses a three-layer authentication model:

1. **Player Accounts** - Username/password registration and login via the lobby web interface. Passwords are hashed with bcrypt.
2. **HMAC-Signed Game Tickets** - The lobby signs HMAC-SHA256 tickets that the game server verifies locally using a shared secret. Tickets contain player identity and room binding.
3. **Bot API Keys** - External bots authenticate via `X-API-Key` header on protected API routes (`POST /api/auth/bot`, `POST /api/rooms`). The lobby validates the key and returns a lobby session for WebSocket access.

Human users register and log in through the lobby at `/register` and `/login`. After authentication, creating or joining a room redirects to the room page (`/rooms/{room_id}`). Game tickets are signed when the room owner starts the game and the lobby transitions to the game server. The `SessionOrApiKeyBackend` checks session cookies first, then the `session_id` query parameter (WebSocket connections only), then falls back to `X-API-Key` header for bot accounts. The backend propagates `account_type` (HUMAN or BOT) from `AuthSession` to `AuthenticatedPlayer`, enabling the `bot_only` policy decorator to distinguish account types at the route level.

### Bot Registration

Register a bot account using the CLI tool:

    uv run python bin/register-bot.py <bot_name>

The API key is printed once and never stored. Set `AUTH_DATABASE_PATH` to control the SQLite database location (default: `backend/storage.db`).

### Running Locally

The `run-local-server.sh` script sets `AUTH_GAME_TICKET_SECRET` automatically and uses `uvicorn --factory` mode to start both servers.

### Room WebSocket Protocol

The lobby room WebSocket uses JSON text frames. Each room has a fixed 4-seat table. Creating a room fills all seats with tsumogiri bots; joining replaces the first available bot seat. The room owner (creator) starts the game explicitly via `start_game` — there is no automatic transition when all players are ready.

Player info objects in all messages use this shape:
```json
{"name": "Alice", "ready": true, "is_bot": false, "is_owner": true}
```
All `players` arrays contain exactly 4 entries (one per seat, in fixed seat order). Bot seats have `is_bot: true` and are always ready.

Client-to-server messages:
- `{"type": "set_ready", "ready": true}` - Toggle ready state (non-owner players only; owner uses `start_game`)
- `{"type": "start_game"}` - Owner starts the game (enabled when all non-owner humans are ready)
- `{"type": "chat", "text": "Hello!"}` - Send chat message
- `{"type": "leave_room"}` - Leave the room
- `{"type": "ping"}` - Heartbeat keep-alive

Server-to-client messages:
- `{"type": "room_joined", "room_id": "...", "player_name": "...", "is_owner": true, "can_start": false, "players": [...]}` - Sent on join
- `{"type": "player_joined", "player_name": "...", "players": [...], "can_start": false}` - Player joined broadcast
- `{"type": "player_left", "player_name": "...", "players": [...], "can_start": false}` - Player left broadcast
- `{"type": "player_ready_changed", "players": [...], "can_start": true}` - Ready state broadcast
- `{"type": "owner_changed", "is_owner": true, "can_start": false, "players": [...]}` - Sent to new owner on host transfer
- `{"type": "chat", "player_name": "...", "text": "..."}` - Chat broadcast
- `{"type": "game_starting", "ws_url": "...", "game_ticket": "...", "game_id": "...", "game_client_url": "/play"}` - Game transition
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

The backend serves the game client directly via a Jinja2 template at `/play/{game_id}`, eliminating the need for a separate static file server. Content-hashed frontend assets (JS, CSS) are served from `/game-assets/`.

### Asset Discovery

Vite produces content-hashed files in `frontend/dist/assets/` and writes `dist/.vite/manifest.json` mapping source entry points to their hashed outputs:

```json
{
  "src/index.ts": {"file": "assets/game-abc123.js", "css": ["assets/game-def456.css"]},
  "src/lobby/index.ts": {"file": "assets/lobby-ghi789.js", "css": ["assets/lobby-jkl012.css"]}
}
```

At startup, the backend reads the Vite manifest via `load_vite_manifest()` and `resolve_vite_asset_urls()`, then sets Jinja2 template globals (`game_js_url`, `game_css_url`, `lobby_js_url`, `lobby_css_url`) with `/game-assets/`-prefixed paths.

### CSP Policy

The security headers middleware applies route-aware Content Security Policy (2 tiers):
- **Lobby pages** (all non-game pages, including rooms) — `script-src 'self'` and `connect-src 'self'` (allows scripts and same-origin connections). Lobby JS loads on all pages.
- **Game pages** (`/play/{game_id}`, `/game-assets/`) — `script-src 'self'` and `connect-src 'self' ws: wss:` (allows scripts and cross-origin WebSocket connections to game servers).

When `LOBBY_VITE_DEV_URL` is set, both tiers also allow scripts and WebSocket from the Vite dev server origin.

### Dev Mode

`run-local-server.sh` sets `LOBBY_VITE_DEV_URL=http://localhost:5173`, which enables Vite dev mode in the lobby backend. Template globals point to the Vite dev server for HMR. The game client is served at `/play` via the lobby (same origin).

## Security Requirements

These practices are mandatory for all lobby code. Violations must be caught in code review.

- **CSRF on all HTML form POST routes**: Every `<form method="POST">` must include a `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">` field. The POST handler must call `validate_csrf(request, form)` before processing any form data. GET handlers that render forms must call `get_or_create_csrf_token()` and pass the token to the template context. Set the CSRF cookie on the response when `is_new` is True. Bot API routes (JSON + API key) are exempt since they don't use cookies for authentication.
- **Route auth policy on every route**: Every route must have exactly one policy decorator (`protected_html`, `protected_api`, `bot_only`, or `public_route`). `validate_route_auth_policy()` fails app startup if any route is missing a policy (fail-closed). Adding a route without a policy decorator is a startup error.
- **Host header validation**: `TrustedHostMiddleware` rejects requests with unrecognized `Host` headers. New deployment hosts must be added to `LOBBY_ALLOWED_HOSTS`.
- **Cookie security**: `AUTH_COOKIE_SECURE` defaults to `true` (production). Local development (`.env.local`) and tests must explicitly set `false`. Session cookies and CSRF cookies must use `httponly=True`, `samesite="lax"`.
- **Session ID query param restricted to WebSocket only**: The `SessionOrApiKeyBackend` must only read `session_id` from query parameters for WebSocket connections (`scope["type"] == "websocket"`). HTTP requests must use cookies only.
- **WebSocket origin check**: Room WebSocket connections must validate the `Origin` header against `LOBBY_WS_ALLOWED_ORIGIN`.
- **CSP headers**: `SecurityHeadersMiddleware` applies route-aware Content Security Policy (2 tiers). Lobby pages allow `script-src 'self'`; game pages add `ws: wss:` to `connect-src`. New routes must fit an existing CSP tier or have an explicit policy added.
- **Sensitive data logging**: Never log passwords, API keys, session IDs, or game tickets at INFO level or above.

## Internal Architecture

- **Server Layer** (`server/`) - Starlette REST API with CORS, auth, and `TrustedHostMiddleware` (host header validation)
- **Settings** (`server/settings.py`) - `LobbyServerSettings` via pydantic-settings (`LOBBY_` env prefix)
- **Auth** (`auth/`) - Starlette `AuthenticationMiddleware` with `SessionOrApiKeyBackend` for cookie/query-param session or `X-API-Key` header authentication; route authorization via `protected_html`, `protected_api`, `bot_only`, and `public_route` policy decorators with startup validation (fail-closed); JSON API routes (`/servers`, `/api/*`) return 401 instead of redirect when unauthenticated
- **CSRF** (`server/csrf.py`) - Double-submit cookie pattern for state-changing HTML POST routes. `get_or_create_csrf_token()` generates tokens on first GET, `validate_csrf()` enforces matching cookie and form field on POST. Protected routes: `/login`, `/register`, `/logout`, `/rooms/new`, `/rooms/{room_id}/join`
- **Views** (`views/`) - Jinja2 templates and view handlers for HTML pages and auth forms; `play_page` serves the built frontend via `play.html` template with manifest-driven asset URLs; `room_page` serves the room UI via `room.html` template; `history_page` renders the history page with recent played games via `history.html` template
- **Registry** (`registry/`) - Game server discovery and health checks
- **Rooms** (`rooms/`) - Room management: `LobbyRoomManager` (room state, TTL reaper), `RoomConnectionManager` (WebSocket broadcasting), WebSocket handler (auth, origin check, game transition), typed message models, room data models

Dependencies on `shared/`:
- `shared.logging.setup_logging` - Timestamped file and stdout logging
- `shared.validators` - String list parsing (CORS origins, allowed hosts) and custom env settings source
- `shared.auth` - `AuthService`, `AuthSessionStore`, `PlayerRepository` for player management; `create_signed_ticket` and `sign_game_ticket` for HMAC-signed game tickets
- `shared.db` - `Database`, `SqlitePlayerRepository` for SQLite-backed player storage, `SqliteGameRepository` for played game queries

## Project Structure

```
ronin/
└── backend/
    └── lobby/
        ├── server/
        │   ├── app.py          # Starlette app factory and route handlers
        │   ├── csrf.py         # CSRF double-submit cookie helpers (token generation, validation)
        │   ├── middleware.py   # SecurityHeadersMiddleware (route-aware CSP), SlashNormalizationMiddleware
        │   └── settings.py     # LobbyServerSettings (pydantic-settings)
        ├── auth/
        │   ├── backend.py      # SessionOrApiKeyBackend (Starlette AuthenticationBackend)
        │   ├── models.py       # AuthenticatedPlayer (Starlette BaseUser)
        │   └── policy.py       # Route auth policy decorators and startup validation
        ├── views/
        │   ├── handlers.py     # View handlers (lobby_page, room_page, play_page, history_page, room creation/join)
        │   ├── auth_handlers.py # Auth handlers (login, register, logout, bot_auth, bot_create_room)
        │   └── templates/
        │       ├── base.html   # Base template with CSS block and scripts block
        │       ├── lobby.html  # Lobby page template
        │       ├── room.html   # Room page template (WebSocket-based room UI)
        │       ├── history.html # History page template (recent played games)
        │       ├── play.html   # Game client template (manifest-driven asset URLs)
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
3. Lobby creates the room locally via `room_manager.create_room(room_id)` (4 bot seats)
4. Lobby redirects (303) to `/rooms/{room_id}`
5. Room page loads and connects to lobby WebSocket at `/ws/rooms/{room_id}`
6. Server auto-joins the player to the room, placing them in the first open seat (seat 0)

### Bot API Flow (POST /api/rooms)
1. Bot authenticates via `X-API-Key` header
2. Lobby creates a room with 4 bot seats. Accepts optional `min_human_players` (1-4, default 1) to require a minimum number of human players before the game can start (the `num_ai_players` parameter is no longer accepted; sending it returns 400)
3. Returns `room_id`, `session_id`, and `ws_url` for WebSocket connection
4. Bot connects to the room WebSocket using the `session_id` query parameter
5. Bot is auto-joined as room owner (seat 0); with the default `min_human_players=1`, `can_start` is `true` immediately since all other seats are bots
6. Bot sends `{"type": "start_game"}` to trigger the game transition

### Game Transition Flow (owner starts game)
1. Non-owner players set ready via `set_ready` WebSocket message
2. Owner sees `can_start: true` when at least `min_human_players` humans have joined and all non-owner humans are ready
3. Owner sends `start_game` via WebSocket
4. Lobby acquires the room's join lock, sets `transitioning=True`, then releases the lock
5. Lobby signs HMAC game tickets for each human player
6. Lobby calls `POST /games` on a game server with player specs (including `num_ai_players` from seat occupancy)
7. On success, lobby sends `game_starting` to each player with their ticket and WS URL
8. Players navigate to game client and connect via `JOIN_GAME`

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
- `LOBBY_CORS_ORIGINS` - Allowed CORS origins as JSON array or CSV string (default: `[]`)
- `LOBBY_ALLOWED_HOSTS` - Allowed hosts for Host header validation as JSON array or CSV string (default: `["localhost", "127.0.0.1", "testserver", "*.local"]`)
- `LOBBY_STATIC_DIR` - Static files directory for CSS (default: `frontend/public`)
- `LOBBY_GAME_CLIENT_URL` - Game client URL for room creation redirects and join links (default: `/play`)
- `LOBBY_WS_ALLOWED_ORIGIN` - Allowed origin for WebSocket connections (CSRF protection). Default: `http://localhost:8710`. Set to `None` to allow all origins
- `LOBBY_GAME_ASSETS_DIR` - Directory containing built game client assets and `.vite/manifest.json` (default: `frontend/dist`)
- `LOBBY_VITE_DEV_URL` - Vite dev server URL for HMR in development (default: empty; set to `http://localhost:5173` when running Vite dev server)

Auth settings (prefixed with `AUTH_`):

- `AUTH_GAME_TICKET_SECRET` - HMAC-SHA256 secret for signing/verifying game tickets (shared between lobby and game server)
- `AUTH_DATABASE_PATH` - Path to the SQLite database file (default: `backend/storage.db`)
- `AUTH_COOKIE_SECURE` - Set cookie Secure flag (default: `true`; set `false` for local HTTP development)
