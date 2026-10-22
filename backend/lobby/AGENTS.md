# Lobby server

Accounts, rooms, matchmaking, game history and the server-rendered pages (`:8710`); it also serves
the built game client and replay files. It hands players to a game server with signed game tickets.
The route table in `server/app.py` is the API reference; `rooms/AGENTS.md` covers room behaviour.

## Structure

* `server/` — `app.py` (route table, `create_app()`, and the `get_app` factory uvicorn runs) and
  `middleware.py` (`SecurityHeadersMiddleware`, slash normalization). `settings.py` (`LOBBY_`) sits
  at the `lobby/` root so every feature may import it.
* `auth/` — `SessionOrApiKeyBackend`, the route policy decorators (`policy.py`) and `csrf.py`.
* `views/` — page and API handlers split by domain, re-exported from `views/__init__.py`
  (`bot_api_handlers.py` is the bot JSON API); Jinja2 templates in `views/templates/`; `assets.py`
  resolves the Vite manifest (or the Vite dev server under `LOBBY_VITE_DEV_URL`) into template
  globals.
* `rooms/` and `matchmaking/` — managers and WebSocket handlers, plus the room's client message
  models; matchmaking is a FIFO queue that starts a 4-human game once 4 players wait, and its client
  sends nothing (the socket only carries the disconnect). The two packages never import each
  other: each gets the occupancy rule (below) as an injected callable.
* `registry/` — game servers from `servers.yaml`, health-checked on every request that needs one,
  with no caching.
* `game_transition.py` — `sign_player_tickets`, `create_game_on_server` and `is_user_playing`,
  shared by rooms and matchmaking; `websocket_utils.py` — `check_origin` and the transport
  contract. After accept, a dead peer raises only `WebSocketDisconnect` (the first failed send) or
  `RuntimeError` (every later send or close), never `ConnectionError`. `send_or_drop` and
  `close_quietly` absorb exactly those, and rooms and matchmaking send to other players through
  them.
* `occupancy.py` — `Occupancy`, the one owner of the occupancy rule.

Services are created in `create_app()` and stored on `app.state`; handlers read them from
`request.app.state`. Tests build the app with `create_app(settings=..., auth_settings=...)`.

## Game start

* A matchmaking match is resolved once, in the handler of the join that completed it: the four
  matched players leave the queue for an in-flight set and are released from it whatever happens,
  so none of them is ever left queued without a handler. A failed creation is terminal: all four
  get `match_failed` and a 4000 close, the client offers to search again, and nothing is retried
  or requeued. A matched player who disconnected meanwhile keeps the seat; the game server replaces
  a seat nobody joins with AI.
* Every game start attempt, room or matchmaking, signs and creates under a fresh `game_id` (a
  room's id is not its game's id). A `GameTransitionError` may mean the game server created the
  game anyway (a timeout after the POST arrived), so a game id is never reused: a retry under the
  same id would collide with the orphan (409) until its pending timeout cancels it.

## Occupancy

* A user is in at most one place: one room seat, the matchmaking queue (queued, or matched while
  their game is created), or one game they are playing. A playing user can neither join a room nor
  queue, and a rejected join gets an `error` naming the reason and a 4000 close.
* Room and queue occupancy is checked synchronously inside `join_room` / `add_player`, in the step
  that seats or queues the user, so the two exclude each other atomically on the event loop.
* "Playing" comes only from the game servers' in-memory sessions (their internal per-user lookup),
  never from `played_games`, whose `ended_at` stays NULL after a crash. The WebSocket handlers ask
  every server in the registry, concurrently under one short deadline, before taking the lock. The
  answer can be stale by then: a start may hand the user's seat or queue place to a new game while
  the lookup is in flight. So each join runs inside an `Occupancy.admitting` window, every attempt
  to create a game calls `hand_to_game` once the game server call is over, whatever its outcome (a
  failure may mean the game exists), and before the seats or the matched players are released, and
  the locked check rejects an admission that was open at that moment as already in a game.
* The lookup fails open (warning, treated as not playing) on a transport error, timeout or
  unexpected status, so a game server outage never locks users out of the lobby. `POST /games`
  refuses a user already playing with 409 as the backstop, which surfaces as an ordinary failed
  start.
* The WebSocket joins are the only gates: room creation and the bot session routes do not check.

## Auth model

* Humans register and log in with username and password (bcrypt) and get a session cookie.
* Bots get an API key from `cd backend && uv run python -m scripts.register_bot <name>` with the
  `AuthSettings` environment set (`AUTH_DATABASE_PATH`, `AUTH_GAME_TICKET_SECRET`), printed once and
  never stored. They send it as `X-API-Key` to
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
