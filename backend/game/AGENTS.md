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
  draw/discard codec, the replay format version.
* `logic/` — the rules engine behind the `GameService` protocol: synchronous, seat-keyed, stateless
  across games, ignorant of connections, time and accounts.
* `replay/` — runs recorded games through the same protocol for tests and profiling, plus the
  Tenhou export; input stays name-keyed and is mapped to seats once, at its boundary.

Import direction is `server` → `session` → `messaging` → `wire` → `logic` (the import-linter
contracts in `backend/pyproject.toml`). Something two layers both need goes down into `wire/` or
`logic/`, never sideways.

## Security requirements

Mandatory for all game server code; review must catch violations.

* Rate-limit every WebSocket after decoding and before processing, so malformed frames always count:
  undecodable frames (non-binary included) are consecutive strikes that close the connection.
* A connection must authenticate (JOIN_GAME or RECONNECT) within the auth timeout or be closed.
* A connection the server closes is evicted from the registry in the same synchronous step, so a
  pipelined or concurrent join/reconnect cannot pick it up.
* A ticket's game must match the path's `game_id`; the ticket checks themselves are `shared/auth/`'s.
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
  INFO or above.

## Tests

State builders live in `tests/conftest.py` and `tests/unit/helpers.py`; `tests/mocks/` fakes the
connection, engine, repository and storage, though lifecycle flows prefer the real seeded engine.
`tests/helpers/` builds a manager over in-memory fakes, signs tickets and drives the endpoint over
real and fake WebSockets; `tests/unit/session/` adds its own helpers and clock fixtures that run
timers without waiting.
Whole-game flows use the replay runner on `tests/integration/replays/fixtures/` or a built
`ReplayInput`, asserting on each step's before/after state.
