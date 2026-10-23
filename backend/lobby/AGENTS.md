# Lobby server

Accounts, rooms, matchmaking, game history and the server-rendered pages (`:8710`); it also serves
the built game client and replay files, and hands players to a game server with signed game tickets.
The route table in `server/app.py` is the API reference; `rooms/AGENTS.md` covers room behaviour.

## Structure

* `server/` — the composition root (`create_app()` builds the services onto `app.state`) and the
  middleware. `settings.py` sits at the `lobby/` root so every feature may import it.
* `auth/` — the session-or-API-key authentication backend, the route policy decorators and CSRF.
* `views/` — page and API handlers by domain (`bot_api_handlers.py` is the bot JSON API), the Jinja2
  templates, and the Vite manifest / dev-server resolution into template globals.
* `rooms/` and `matchmaking/` — managers and WebSocket handlers. Matchmaking is a FIFO queue that
  starts a 4-human game once 4 players wait; its client sends nothing, so it needs no rate limit.
  The two never import each other: they share `start_game` and `LobbyPlayer`, and each gets the
  occupancy rule as an injected callable.
* `game_transition.py` — the one game start for rooms and matchmaking, the game server client calls
  and the "is this user playing" lookup. `websocket_utils.py` — the WebSocket `Origin` check.
* `players.py` — `LobbyPlayer`, one connected user and the only holder of its socket. Every send or
  close is an enqueue, so no handler, broadcast or reaper tick ever waits on a slow or dead peer.
* `occupancy.py` — the one owner of the occupancy rule.
* The one game server is two settings never derived from each other: the internal URL the lobby
  calls and the public WebSocket origin it hands clients.
* Tests build the app through the fixtures in `tests/conftest.py`.

## Game start

* Every attempt creates the game under a fresh game id (a room's id is not its game's id): a failed
  call may mean the game server created the game anyway, and a retry under the same id would
  collide with that orphan.
* A failure before the game server confirms creation raises `GameStartError`, whose `reason` is the
  text players see; each caller recovers its own way. After confirmation delivery only enqueues, so
  one slow player delays nobody else.
* A match is resolved once, by the join that completed it, and a failed creation is terminal: the
  four are told and closed, nothing is retried or requeued. A matched player who disconnected
  meanwhile keeps the seat; the game server fills a seat nobody joins with AI.

## Occupancy

* A user is in at most one place: one room seat, the matchmaking queue (queued or matched), or one
  game they are playing. A rejected join is told the reason and closed.
* Room and queue occupancy is checked synchronously inside the step that seats or queues the user,
  so the two exclude each other atomically on the event loop and the lobby needs no lock.
* "Playing" comes only from the game server's in-memory sessions, never from `played_games`, whose
  `ended_at` stays NULL after a crash. The handlers ask the game server before the occupancy check,
  and `Occupancy` rejects a join whose answer a concurrent game start made stale.
* The lookup fails open (treated as not playing) on a transport failure, a timeout or an unexpected
  status, so a game server outage never locks users out; the game server refusing a user already
  playing is the backstop.
* The WebSocket joins are the only gates: room creation does not check.

## Auth model

* Humans register and log in with username and password and get a session cookie. Every session is
  a human's; bots have none.
* Bots register through `scripts/register_bot.py` and get an API key, printed once and never stored.
  They send it as `X-API-Key` on the bot API and the WebSocket handshakes, with the configured
  `Origin`; from the handshake on, a bot runs the human code path.
* The backend tries the session cookie first and falls back to a BOT account's `X-API-Key`, so a
  valid cookie wins over a key. `bot_only` routes answer JSON errors, never a login redirect.
* Game tickets are signed when a game starts and verified by the game server with the shared secret.

## Security requirements

Mandatory for all lobby code; review must catch violations.

* Every HTML form POST validates the CSRF token (`auth/csrf.py`); bot API routes are exempt.
* Every HTTP route gets exactly one policy decorator (`protected_html`, `bot_only`, `public_route`);
  startup fails for a `Route` without one. WebSocket routes authenticate inside the handler.
* Unknown `Host` headers are rejected; a new deployment host goes in the allowed-hosts setting.
* Session and CSRF cookies are HttpOnly, SameSite=Lax and Secure by default; only the test
  environment turns Secure off.
* Credentials never travel in a URL: uvicorn and Traefik log every path with its query string.
* Room and matchmaking WebSockets refuse any socket whose `Origin` is not exactly the configured
  one, a setting every deployment must supply.
* Two CSP tiers: lobby pages (same-origin connect) and game pages (`/play/*`, `/game-assets/`,
  external WebSockets allowed). A new route fits a tier or gets an explicit policy.
* Replay serving resolves paths only through `shared.storage.replay_file_path` and keeps its id
  checks, path traversal protection and size limit.
* Passwords, API keys, session ids and game tickets are never logged at INFO or above.
