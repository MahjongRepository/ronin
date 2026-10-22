# Game server

Real-time Riichi Mahjong over WebSocket (`:8711`). The lobby creates a game with `POST /games` and
hands each player a signed game ticket; players then connect to `/ws/{game_id}` and play. `logic/`,
`session/` and `messaging/` each have an `AGENTS.md` with their own model and rules.

## Layers

* `server/` — inbound: Starlette app (`app.py`, `get_app` factory), WebSocket endpoint
  (`websocket.py`), `MessageRouter` (`router.py`: parses client messages, verifies game tickets on
  JOIN_GAME / RECONNECT, dispatches to `SessionManager`), `TokenBucket` rate limiter,
  `GameServerSettings`. The router talks to the transport only through `ConnectionProtocol`, so
  tests run it on `MockConnection`.
* `session/` — `SessionManager`: pending games (`PlayerSpec` is its input), joins, disconnects,
  reconnects, timers, replay collection.
* `messaging/` — outbound: MessagePack encoder, client message models, wire shaping of events
  (`event_payload.py`).
* `wire/` — the wire format both the server and the replay tool read: integer event and result
  codes (`enums.py`, `events.py`), the packed draw/discard codec (`compact.py`) and
  `REPLAY_VERSION` (`replay_format.py`).
* `logic/` — the rules engine behind the `GameService` protocol (`MahjongGameService`): synchronous,
  seat-keyed; every call that can change a game returns its events and what the game waits for next
  (`GameUpdate`: `ServiceEvent`s plus an `Awaiting`), and it knows nothing about connections, time or
  accounts.
* `replay/` — runs recorded games through the same `GameService` protocol (`runner.py`: `run_replay`;
  `loader.py`: `load_replay_from_file` / `load_replay_from_string`) for tests and profiling. It
  depends on `logic` and `wire` only. Replay input stays name-keyed; the runner maps names to the seats
  `start_game` returns once, at its boundary.

Import direction is `server` → `session` → `messaging` → `wire` → `logic`, enforced by the
import-linter contracts in `pyproject.toml` (see `backend/AGENTS.md`, "Boundaries"). Something two
layers both need goes down into `wire/` or `logic/`, never sideways.

## Security requirements

Mandatory for all game server code; review must catch violations.

* Every WebSocket endpoint rate-limits with `TokenBucket`: check `bucket.consume()` after decoding
  and before processing; when empty, send `RATE_LIMITED` and skip the message.
* Undecodable messages count consecutive strikes; `_MAX_DECODE_ERRORS` closes with 4004, and a valid
  message resets the count. Rate limiting runs after decode so malformed messages always count.
* A connection must authenticate (JOIN_GAME or RECONNECT) within `_AUTH_TIMEOUT_SECONDS` or be closed
  with 4001. Cancel the timeout task on authentication, disconnect, stale-connection eviction and
  shutdown, and remove the connection from `_connections` before closing it so a concurrent
  join/reconnect cannot pick it up.
* `verify_game_ticket()` checks the HMAC-SHA256 signature; numeric, finite timestamps (reject
  `bool`, `inf`, `NaN`); `issued_at` not in the future beyond `CLOCK_SKEW_SECONDS`;
  `expires_at > issued_at`; lifetime within `TICKET_TTL_SECONDS + CLOCK_SKEW_SECONDS`; and expiry.
  All must pass, and the ticket's game must match the path's `game_id`.
* REST bodies are read with `request.stream()` and a hard size cutoff, never `await request.body()`
  on untrusted input; handle `ClientDisconnect`.
* Validate the WebSocket `game_id` path parameter against `_GAME_ID_PATTERN` and
  `_MAX_GAME_ID_LENGTH` before accepting.
* Every background task has an owner and an exception boundary. A sleeping pending, auth or turn
  timer is cancelled when its game or connection goes; once it fires it detaches itself, so no
  cancel path cancels it while it finishes a game, and a fired timer that a stop, cancel or re-arm
  superseded while it waited for the game lock drops its default action. A connection's writer task
  is owned by its endpoint (`websocket_endpoint`): started after accept and stopped once the
  disconnect is handled, so `SessionManager` holds no socket state. The app lifespan opens the
  database and, on the way out, awaits `SessionManager.shutdown()` (sleeping tasks cancelled, fired
  ones awaited) before draining and closing it. An unexpected error in a task that has a game ends that game
  through `fail_game`; the auth timeout, which has none, logs and closes the socket. A new kind of
  task joins these paths.
* Liveness is the WebSocket protocol ping, run by uvicorn (`deploy/AGENTS.md`); the server keeps no
  application-level ping or heartbeat. A missed pong closes the transport, and the endpoint's
  disconnect path runs once uvicorn reports the connection lost, which waits for the transport's
  write buffer to drain: at once for a peer with nothing pending, and for one whose buffer is stuck
  only through the connection writer's send deadline (below), which terminates it.
* Sends and closes never raise or wait for a dead or slow socket (an encoding error still raises
  at the caller): `WebSocketConnection` queues them (bounded) for its writer, FIFO, a close last and
  nothing after it. A connection whose queue overflows, whose send outlasts the send deadline or
  whose write fails is terminated without a close frame, and a dead socket surfaces only at
  receive, as `ConnectionError`, so the endpoint's disconnect path seats an AI player. The endpoint
  lets the writer flush a close it queued (within the send deadline) before returning, so the
  client gets its close code.
* The router's game action, JOIN_GAME, RECONNECT and disconnect handlers are the same kind of
  boundary (`SessionManager.fail_connection`, with the game captured before the call): any exception
  fails that game, or with no game is logged and the socket closed with 1011; a connection the game
  does not seat leaves the registry before its 1011 close. Inside its message loop
  `websocket_endpoint` closes with 1011 on anything else that reaches it, so no exception from
  handling a message leaves the ASGI app; a non-binary frame is client input and counts as a decode
  strike.
* Concealed hand tiles are logged at DEBUG only; game tickets and session tokens are never logged at
  INFO or above.

## Tests

* `tests/conftest.py` builders (`create_player`, `create_round_state`, `create_game_state`) and
  `tests/unit/helpers.py` (`_update_round_state`, `_update_player`) build frozen state.
* `MockConnection` and `MockGameService` (`tests/mocks/`) test routing and sessions without sockets;
  `tests/unit/session/helpers.py` (`create_started_game`, `disconnect_and_reconnect`) drives the
  session lifecycle; `tests/helpers/auth.py` (`make_test_game_ticket`) signs tickets;
  `tests/helpers/websocket.py` drives a `TestClient` WebSocket; `tests/helpers/fake_websocket.py`
  (`FakeWebSocketClient`) is the ASGI client side of a real Starlette WebSocket whose writes can be
  held or failed, for the connection writer and the endpoint.
* Whole-game flows use the replay runner with fixtures in `tests/integration/replays/fixtures/` or a
  built `ReplayInput`, asserting on each step's `state_before` / `state_after`.
