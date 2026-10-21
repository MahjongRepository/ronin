# Game server

Real-time Riichi Mahjong over WebSocket (`:8711`). The lobby creates a game with `POST /games` and
hands each player a signed game ticket; players then connect to `/ws/{game_id}` and play. `logic/`,
`session/` and `messaging/` each have an `AGENTS.md` with their own model and rules.

## Layers

* `server/` — transport: Starlette app (`app.py`, `get_app` factory), WebSocket endpoint
  (`websocket.py`), `TokenBucket` rate limiter, `GameServerSettings`.
* `messaging/` — `MessageRouter`, MessagePack encoder, client message models, wire shaping of
  events. Talks to the transport only through `ConnectionProtocol`, so tests run it on
  `MockConnection`.
* `session/` — `SessionManager`: pending games, joins, disconnects, reconnects, timers, replay
  collection.
* `logic/` — the rules engine behind the `GameService` interface (`MahjongGameService`); returns
  `list[ServiceEvent]` and knows nothing about connections.
* `replay/` — runs recorded games through the public `GameService` API (`runner.py`: `run_replay`;
  `loader.py`: `load_replay_from_file` / `load_replay_from_string`) for tests and profiling.
* `wire/enums.py` — integer wire codes shared by `messaging` and `replay`.

Import direction is enforced by `tests/integration/test_architecture_boundary.py`: at runtime,
`logic` never imports `replay` and `messaging` never imports `session`; imports under
`if TYPE_CHECKING:` are allowed. Put a shared wire type in `wire/` rather than crossing those lines.

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
* Every background task is cancelled on teardown. Server shutdown calls
  `cancel_all_pending_timeouts()` and `cancel_all_auth_timeouts()`; a game's turn timers and
  heartbeat are cancelled when the game is cleaned up. A new kind of task joins one of those paths.
* Concealed hand tiles are logged at DEBUG only; game tickets and session tokens are never logged at
  INFO or above.

## Tests

* `tests/conftest.py` builders (`create_player`, `create_round_state`, `create_game_state`) and
  `tests/unit/helpers.py` (`_update_round_state`, `_update_player`) build frozen state.
* `MockConnection` and `MockGameService` (`tests/mocks/`) test routing and sessions without sockets;
  `tests/unit/session/helpers.py` (`create_started_game`, `disconnect_and_reconnect`) drives the
  session lifecycle; `tests/helpers/auth.py` (`make_test_game_ticket`) signs tickets;
  `tests/helpers/websocket.py` drives a `TestClient` WebSocket.
* Whole-game flows use the replay runner with fixtures in `tests/integration/replays/fixtures/` or a
  built `ReplayInput`, asserting on each step's `state_before` / `state_after`.
