# Lobby server

Accounts, rooms, matchmaking, game history and the server-rendered pages (`:8710`); it also hosts
the game client and serves replay files, and hands players to a game server with signed game tickets.
The route table in `server/app.py` is the API reference; `rooms/AGENTS.md` covers room behaviour.

## Structure

* `server/` — the composition root (`create_app()` builds the services onto `app.state`) and the
  middleware. `settings.py` sits at the `lobby/` root so every feature may import it.
* `auth/` — the session-or-API-key authentication backend, the route policy decorators and CSRF.
* `views/` — page and API handlers by domain (`bot_api_handlers.py` is the bot JSON API), the Jinja2
  templates, and the lobby app's Vite manifest / dev-server resolution into template globals.
  `game_client.py` hosts the game client, a separate app the lobby knows only by its built
  directory: it answers the game pages with that app's `index.html` and serves its files under
  `/game-assets/`, or proxies both to the app's Vite dev server when `game_client_dev_url` is set.
  The proxy exists only for local runs, so the game page keeps the lobby's origin and the
  `sessionStorage` handoff (`docs/architecture.md`, Game client contract) works.
* `rooms/` and `matchmaking/` — managers and WebSocket handlers. Matchmaking is a FIFO queue that
  starts a 4-human game once 4 players wait; its client sends nothing, so it needs no rate limit.
  The two never import each other: they share `start_game` and `LobbyPlayer`, and each gets the
  occupancy rule as an injected callable.
* `game_transition.py` — the one game start for rooms and matchmaking, the game server client calls,
  the "is this user playing" lookup and the recovery of a lost handoff. `websocket_utils.py` — the
  socket prologue rooms and matchmaking share (`Origin` check, auth, accept, the writer's lifetime);
  each handler decides what an unexpected error does.
* The lobby calls the game server through one HTTP client per app, built in `create_app()` and
  closed in the lifespan. Its idle connections expire well before the game server's keep-alive
  timeout (uvicorn's 5s default), since a start sent on a connection the server is closing fails
  ambiguously. Each call keeps its own deadline rather than the client's default.
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
* A failure before the game server confirms creation raises `GameStartError` with a fixed reason
  code; the game server's own text goes only to the log. Each caller recovers its own way: a room
  sends the code, matchmaking `match_failed`. A 409 from the game server is its occupancy backstop
  (the fresh id rules out a duplicate game), so its code is `player_in_game`. After confirmation
  delivery only enqueues, so one slow player delays nobody else.
* A match is resolved once, by the join that completed it, and a failed creation is terminal: the
  four are told and closed, nothing is retried or requeued. A matched player who disconnected
  meanwhile keeps the seat; the game server fills a seat nobody joins with AI.

## Occupancy

* A user is in at most one place: one room seat, the matchmaking queue (queued or matched), or one
  game they are playing. A rejected join is told the reason and closed.
* A join to the place the user already holds (their seat in the same room, full or not, or their
  unmatched queue entry) takes it over instead: the new connection keeps the seat, readiness and
  arrival (so host succession) or the queue position, and the old one is told
  `replaced_by_new_connection` and closed. Lobby sockets never reconnect, so this is how a reload
  or a second tab gets past a dead socket the server has not noticed yet. When two connections of
  one user join at once, the last one admitted wins, which is the one whose playing lookup finished
  last, not necessarily the newest. A place is never traded for another, and never taken over once
  its game is being created: a transitioning room refuses every join, and a matched user is
  refused as `match_starting` (by a room join too), retryable answers that the handoff recovery
  turns into the game once it exists.
* Everything keyed by connection (ready, start, leave, chat, cleanup) misses for a taken-over
  connection, so its buffered input and late cleanup change nothing.
* Room and queue occupancy is checked synchronously inside the step that seats or queues the user,
  so the two exclude each other atomically on the event loop and the lobby needs no lock.
* The occupancy rule runs before anything else in that step (a room's existence included), so a
  join that a start handed to its game during the lookup is always refused as `already_in_game`
  and handed that game, even once the start has removed the room.
* "Playing" comes only from the game server's in-memory sessions, never from `played_games`, whose
  `ended_at` stays NULL after a crash. The handlers ask the game server before the occupancy check,
  and `Occupancy` rejects a join whose answer a concurrent game start made stale.
* The lookup fails open (treated as not playing) on a transport failure, a timeout or an unexpected
  status, so a game server outage never locks users out; the game server refusing a user already
  playing is the backstop.
* The WebSocket joins are the only gates: room creation does not check.

## Handoff recovery

* A join refused as `already_in_game` is answered with the user's live game as `game_starting`
  when the game server can name it, so a lost handoff is repaired by any lobby join; the game page
  recovers through `GET /api/game-session`. The room page of a room that is gone redirects a
  playing user to their game's page (to the lobby when they play none or the lookup fails). The flow is in `docs/architecture.md`.
* Recovery returns the participant's own ticket from the game server; the lobby never caches or
  re-signs tickets. It asks only for the authenticated user's id, and its lookup never fails open:
  a failure keeps `already_in_game` (or answers 503), distinct from "no game".

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
* Every HTTP route gets exactly one policy decorator (`protected_html`, `protected_json`, `bot_only`,
  `public_route`); startup fails for a `Route` without one. WebSocket routes authenticate inside the
  handler. `protected_json` is for JSON a page script fetches: a JSON 401, never a login redirect.
* Unknown `Host` headers are rejected; a new deployment host goes in the allowed-hosts setting.
* Session and CSRF cookies are HttpOnly, SameSite=Lax and Secure by default; only the test
  environment turns Secure off.
* Credentials never travel in a URL: uvicorn and Traefik log every path with its query string. A
  response carrying a credential (a game ticket) is `Cache-Control: no-store`.
* The internal API secret is sent only to the game server, as a bearer header; no page or browser
  response ever holds it.
* Room and matchmaking WebSockets refuse any socket whose `Origin` is not exactly the configured
  one, a setting every deployment must supply.
* Two CSP tiers: lobby pages (same-origin connect) and game pages (`/play/*`, `/game-assets/`,
  external WebSockets allowed). A new route fits a tier or gets an explicit policy.
* Replay serving resolves paths only through `shared.storage.replay_file_path` and keeps its id
  checks, path traversal protection and size limit.
* Passwords, API keys, session ids and game tickets are never logged at INFO or above.
