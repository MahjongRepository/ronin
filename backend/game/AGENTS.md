# Game server

Real-time Riichi Mahjong over WebSocket. The lobby creates a game over REST and hands each player a
signed game ticket; players then connect by WebSocket and play. `logic/`, `session/` and
`messaging/` each have an `AGENTS.md` with their own model and rules.

## Layers

* `server/` — inbound: the Starlette app and REST routes, the WebSocket endpoint and the message
  router that verifies tickets and dispatches to the session manager; it reaches the transport only
  through a protocol, so routing is tested without sockets.
* `session/` — the registry of live games and their lifecycle: pending games, joins, disconnects,
  reconnects, timers, replay collection, the one end of every game.
* `messaging/` — outbound: MessagePack encoding, client message models, wire shaping of events.
* `wire/` — the wire format both the server and the replay tool read: integer codes, the packed
  draw/discard codec, the replay storage codec and format version, and the replay-only record types, whose `t` codes share
  the events' space without taking one of their values, so a live wire code never changes for them.
* `logic/` — the rules engine behind the `GameService` protocol: synchronous, seat-keyed, stateless
  across games, ignorant of connections, time and accounts.
* `replay/` — runs recorded games through the same protocol for tests and profiling, plus the
  Tenhou export; input stays name-keyed and is mapped to seats once, at its boundary. A replay
  records an immutable rules-profile ID and sparse effective settings overrides on its `game_started`
  record. Both the runner and the export resolve it through `logic/`'s profile registry, never current
  defaults. The browser uses explicit viewing settings and recorded events, without a profile registry
  or engine execution. Replay storage uses independent MessagePack records, integer metadata keys and
  a binary seed under one gzip stream; `wire/` keeps metadata keys numeric throughout and restores only the hexadecimal seed at the read boundary.
  Builders and consumers reference `WireKey` directly; string keys inside settings and score maps are data.
  A change to the replay records is followed by
  `make generate-replay-fixtures`, which re-records the v2 game client's replay fixtures.

Import direction is `server` → `session` → `messaging` → `wire` → `logic` (the import-linter
contracts in `backend/pyproject.toml`). Something two layers both need goes down into `wire/` or
`logic/`, never sideways.

## Security requirements

Mandatory for all game server code; review must catch violations.

* Rate-limit every WebSocket after decoding and before processing, so malformed frames always count:
  every frame is charged once, an over-budget malformed frame gets no reply or log, and undecodable
  frames (non-binary included) are consecutive strikes that close the connection. A resync request,
  which costs a whole snapshot, also draws on a far tighter budget of its own per connection.
* A connection must authenticate (JOIN_GAME or RECONNECT) within the auth timeout or be closed.
* A connection the server closes is evicted from the registry in the same synchronous step, so a
  pipelined or concurrent join/reconnect cannot pick it up.
* A ticket's game must match the path's `game_id`; the ticket checks themselves are `shared/auth/`'s.
* A REST route that returns a credential (the participant ticket lookup) answers only the internal
  API secret as a bearer token, compared in constant time, and marks every answer
  `Cache-Control: no-store`: in development the game server's CORS lets the lobby origin's scripts
  read its GETs, so its bind address is no isolation. A route that spends real CPU on a public
  request (the Tenhou export) answers only that secret too, so it runs only behind the lobby's
  rate-limited route, and so does a route that ends a game on the lobby's word (the withdrawal).
* `/status` answers without auth, so it carries only process-wide totals since start and gauges, never
  per-user data.
* Read REST bodies with `request.stream()` and a hard size cutoff, never `await request.body()` on
  untrusted input; handle `ClientDisconnect`.
* Validate the `game_id` path parameter before the handshake; the reject and the accept go through
  `shared/`'s handshake helpers.
* Every background task has an owner and an error boundary: a task with a game fails that game, the
  auth timeout logs and closes. The endpoint owns the writer task, so the session holds no socket
  state; the lifespan shuts the session manager down before closing the database.
* Liveness is uvicorn's WebSocket protocol ping (`deploy/AGENTS.md`); the server runs no ping or
  heartbeat of its own.
* Sends and closes never raise or wait on a dead or slow socket (an encoding error still raises);
  a dead socket surfaces only at receive, where the disconnect path seats an AI player.
* No exception from handling a message leaves the ASGI app: a router handler that reaches a game
  fails that game, anything else closes the socket as an internal error.
* Concealed hand tiles are logged at DEBUG only; game tickets and session tokens are never logged at
  INFO or above. A message that fails validation is answered and logged without its input or the
  validation text (a pydantic message can quote the input): only the error types.

## Tests

State builders live in `tests/conftest.py` and `tests/unit/helpers.py`; `create_dealt_game_state` stages
a running round from explicit players and gives the walls every tile not held in their hands, melds or
discards. `tests/mocks/` fakes the connection, engine, repository and storage, though lifecycle flows
prefer the real seeded engine.
`tests/helpers/` builds a manager over in-memory fakes, signs tickets, drives the endpoint over
real and fake WebSockets and holds hand staging shared by unit and integration tests; `tests/unit/session/` adds its own helpers and clock fixtures that run
timers without waiting.
Whole-game flows use the replay runner on `tests/integration/replays/fixtures/` or a built
`ReplayInput`, asserting on each step's before/after state.
A change to what the session sends a seat (a payload, a stamp, a delivery rule) is followed by
`make generate-seat-scenarios`: `scripts/seat_scenarios/` plays scripted clients through the real
`SessionManager` and `MessageRouter` over in-memory sockets, on an event loop whose clock jumps to each
timer instead of waiting, and records what each seat received and sent for the v2 client's tests and
storybook. A socket the server closes runs the router's disconnect as the endpoint does, and a scripted
step that falls on the moment a server timer fires is refused, since their order would be the loop's.
