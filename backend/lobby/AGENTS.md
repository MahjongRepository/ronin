# Lobby server

Accounts, rooms, matchmaking, game history and the server-rendered pages (`:8710`); it also serves
the built game client and replay files. It hands players to a game server with signed game tickets.
The route table in `server/app.py` is the API reference; `rooms/AGENTS.md` covers room behaviour.

## Structure

* `server/` — `app.py` (route table, `create_app()`, and the `get_app` factory uvicorn runs),
  `settings.py` (`LOBBY_`), `middleware.py` (`SecurityHeadersMiddleware`, slash normalization),
  `csrf.py`.
* `auth/` — `SessionOrApiKeyBackend` and the route policy decorators (`policy.py`).
* `views/` — page and API handlers split by domain, re-exported from `views/__init__.py`; Jinja2
  templates in `views/templates/`; `assets.py` resolves the Vite manifest (or the Vite dev server
  under `LOBBY_VITE_DEV_URL`) into template globals.
* `rooms/` and `matchmaking/` — managers, WebSocket handlers and message models; matchmaking is a
  FIFO queue that starts a 4-human game once 4 players wait, and rejects users already in a room
  (`already_in_room`) or already queued (`already_in_queue`).
* `registry/` — game servers from `servers.yaml`, health-checked on every request that needs one,
  with no caching.
* `game_transition.py` — `sign_player_tickets` and `create_game_on_server`, shared by rooms and
  matchmaking; `websocket_utils.py` — `check_origin`.

Services are created in `create_app()` and stored on `app.state`; handlers read them from
`request.app.state`. Tests build the app with `create_app(settings=..., auth_settings=...)`.

## Auth model

* Humans register and log in with username and password (bcrypt) and get a session cookie.
* Bots get an API key from `cd backend && AUTH_DATABASE_PATH=storage.db uv run python -m
  scripts.register_bot <name>` (printed once, never stored). They send it as `X-API-Key` to
  `POST /api/rooms` or `POST /api/matchmaking/join`, and open the returned `ws_url` with
  `?session_id=...`.
* `SessionOrApiKeyBackend` takes the session id from the cookie, or from the `session_id` query
  parameter on a WebSocket that has no cookie; if that session is not valid it falls back to a bot's
  `X-API-Key` (HTTP and WebSocket). It carries `account_type` (HUMAN or BOT) so `bot_only` can tell
  them apart. `protected_api` routes answer 401 instead of redirecting to login; replay retrieval
  (`/api/replays/{game_id}`) is public.
* Game tickets are HMAC-SHA256, signed when a game starts, and verified by the game server with the
  shared `AUTH_GAME_TICKET_SECRET`. On `game_starting` the client gets its ticket and the game
  server's `ws_url`.

## Security requirements

Mandatory for all lobby code; review must catch violations.

* CSRF on every HTML form POST: the form has a hidden `csrf_token` field, the POST handler calls
  `validate_csrf(request, form)` before touching the data, and the GET handler that renders it calls
  `get_or_create_csrf_token()`, passes the token to the template and sets the cookie when `is_new`.
  Bot API routes (JSON + API key) are exempt.
* Every HTTP route gets exactly one policy decorator (`protected_html`, `protected_api`, `bot_only`,
  `public_route`). `validate_route_auth_policy()` fails startup only for a `Route` with no policy at
  all; it does not catch stacked decorators, and `Mount`s (static files) are exempt. WebSocket routes
  authenticate inside the handler.
* `TrustedHostMiddleware` rejects unknown `Host` headers; a new deployment host goes in
  `LOBBY_ALLOWED_HOSTS`.
* Session and CSRF cookies are `httponly=True`, `samesite="lax"`, Secure per `AUTH_COOKIE_SECURE`.
* `session_id` is read from the query string only when `scope["type"] == "websocket"`; HTTP
  sessions come from the cookie only.
* Room and matchmaking WebSockets check `Origin` against `LOBBY_WS_ALLOWED_ORIGIN` (`check_origin`).
* `SecurityHeadersMiddleware` has two CSP tiers: lobby pages (`script-src 'self'`,
  `connect-src 'self'`) and game pages (`/play/*`, `/game-assets/`, which add `ws: wss:` to
  `connect-src`). A new route fits a tier or gets an explicit policy.
* Replay serving (`views/replay_handlers.py`) resolves paths only through
  `shared.storage.replay_file_path`, keeps the id length checks, path traversal protection and the
  size limit.
* Passwords, API keys, session ids and game tickets are never logged at INFO or above.
