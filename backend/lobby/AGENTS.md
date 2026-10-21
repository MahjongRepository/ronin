# Lobby server

Accounts, rooms, matchmaking, game history and the server-rendered pages (`:8710`); it also serves
the built game client. It hands players to a game server with signed game tickets. Reference, read
when the task touches it:

* `docs/lobby-api.md` — routes, room and matchmaking WebSocket messages, the bot flow.
* `docs/configuration.md` — `LOBBY_*` and `AUTH_*` environment variables.

## Structure

* `server/` — `app.py` (route table, `create_app()`, and the `get_app` factory uvicorn runs),
  `settings.py` (`LOBBY_` prefix), `middleware.py` (`SecurityHeadersMiddleware`, slash
  normalization), `csrf.py`.
* `auth/` — `SessionOrApiKeyBackend` and the route policy decorators (`policy.py`).
* `views/` — page and API handlers split by domain (`handlers.py`, `auth_handlers.py`,
  `history_handlers.py`, `replay_handlers.py`, `game_handlers.py`), re-exported from
  `views/__init__.py`; Jinja2 templates in `views/templates/`; `assets.py` resolves the Vite
  manifest into template globals.
* `rooms/` — `LobbyRoomManager` (room state, TTL reaper), `RoomConnectionManager` (broadcast), the
  room WebSocket handler and its message models.
* `matchmaking/` — `MatchmakingManager` (FIFO queue under an `asyncio.Lock`), its WebSocket handler
  and message models.
* `registry/` — game servers from `servers.yaml`, health-checked on every request that needs one.
* `game_transition.py` — `sign_player_tickets` and `create_game_on_server`, shared by rooms and
  matchmaking; `websocket_utils.py` — `check_origin`.
* Accounts, auth sessions, game tickets and the database come from `shared/` (`shared.auth`,
  `shared.db`, `shared.storage`).

Services are created in `create_app()` and stored on `app.state`; handlers read them from
`request.app.state`. Tests build the app with `create_app(settings=..., auth_settings=...)`.

## Auth model

* Humans register and log in with username and password (bcrypt) and get a session cookie. Bots
  authenticate with `X-API-Key` (`docs/lobby-api.md`).
* `SessionOrApiKeyBackend` tries the session cookie, then the `session_id` query parameter
  (WebSockets only), then `X-API-Key`, and carries `account_type` (HUMAN or BOT) so `bot_only` can
  tell them apart. JSON routes (`/servers`, `/api/*`) answer 401 instead of redirecting to login.
* Game tickets are HMAC-SHA256, signed when a game starts, with the secret shared with the game
  server (`AUTH_GAME_TICKET_SECRET`).

## Game transition

The room owner sends `start_game`. Under the room's `join_lock` the lobby only sets
`transitioning=True`, then releases the lock before any network call; joins arriving meanwhile get
`room_transitioning` instead of waiting. It then signs a ticket per human, calls the game server's
`POST /games` (with `num_ai_players` from the seats bots hold), and sends each player
`game_starting`. On failure it clears `transitioning`, which resets the ready flags, and
rebroadcasts the room state. Matchmaking runs the same steps once 4
players are queued, with no AI players.

## Security requirements

Mandatory for all lobby code; review must catch violations.

* CSRF on every HTML form POST: the form has a hidden `csrf_token` field, the POST handler calls
  `validate_csrf(request, form)` before touching the data, and the GET handler that renders it calls
  `get_or_create_csrf_token()`, passes the token to the template and sets the cookie when `is_new`.
  Bot API routes (JSON + API key) are exempt.
* Every HTTP route has exactly one policy decorator (`protected_html`, `protected_api`, `bot_only`,
  `public_route`); `validate_route_auth_policy()` fails startup otherwise. WebSocket routes
  authenticate inside the handler.
* `TrustedHostMiddleware` rejects unknown `Host` headers; a new deployment host goes in
  `LOBBY_ALLOWED_HOSTS`.
* Session and CSRF cookies are `httponly=True`, `samesite="lax"`, Secure per `AUTH_COOKIE_SECURE`
  (default `true`; `.env.local` and tests set `false`).
* `session_id` is read from the query string only when `scope["type"] == "websocket"`; HTTP uses
  cookies only.
* Room and matchmaking WebSockets check `Origin` against `LOBBY_WS_ALLOWED_ORIGIN` (`check_origin`).
* `SecurityHeadersMiddleware` has two CSP tiers: lobby pages (`script-src 'self'`,
  `connect-src 'self'`) and game pages (`/play/*`, `/game-assets/`, which add `ws: wss:` to
  `connect-src`). A new route fits a tier or gets an explicit policy.
* Replay serving resolves paths only through `shared.storage.replay_file_path`, with the minimum id
  length, path traversal protection and the size limit.
* Passwords, API keys, session ids and game tickets are never logged at INFO or above.
