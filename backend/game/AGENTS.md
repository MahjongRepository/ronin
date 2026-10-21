# Game server

Real-time Riichi Mahjong over WebSocket (`:8711`). The lobby creates games here and hands players
signed game tickets; this server runs the game itself. Reference, read when the task touches it:

* `docs/game-protocol.md` — REST and WebSocket messages, event codes, error codes, replay files.
* `docs/game-rules.md` — the ruleset and configurable settings the engine implements. Read it before
  changing anything in `logic/`.

## Layers

* `server/` — transport: Starlette app (`app.py`), WebSocket endpoint, rate limiter, settings
  (`GAME_` prefix).
* `messaging/` — `MessageRouter`, MessagePack encoder, client message models (`types.py`), wire
  shaping of events (`event_payload.py`, `compact.py`). Talks to the transport only through
  `ConnectionProtocol`, so it runs in tests on `MockConnection`.
* `session/` — `SessionManager` (pending games, joins, reconnects, per-game locks), delegating to
  `SessionStore`, `TimerManager`, `HeartbeatMonitor` and `ReplayCollector`.
* `logic/` — the rules engine behind the `GameService` interface (`MahjongGameService`). Returns
  `list[ServiceEvent]`; knows nothing about connections.
* `replay/` — runs recorded games through the public `GameService` API (`run_replay`, `ReplayLoader`)
  for tests and profiling.
* `wire/enums.py` — integer wire codes shared by `messaging` and `replay`.

Import direction is enforced by `tests/integration/test_architecture_boundary.py`: `logic` never
imports `replay`, and `messaging` never imports `session`. Put a shared wire type in `wire/`
rather than crossing those lines.

## Engine model

* State is frozen Pydantic (`logic/state.py`: `MahjongGameState` → `MahjongRoundState` →
  `MahjongPlayer`, plus `PendingCallPrompt`); update with `model_copy(update=...)` and the helpers
  in `state_utils.py`. Settings live only on `MahjongGameState`. The wall is a frozen `Wall`
  (`wall.py`); melds are `FrozenMeld`, converted to the `mahjong` library's `Meld` only at its
  boundary.
* Domain events (`logic/events.py`) carry integer tile ids only (136-format); `convert_events()`
  wraps them in `ServiceEvent` with a `BroadcastTarget` or `SeatTarget`.
* One dispatch pipeline for humans and AI: `handle_action()` → `_dispatch_and_process()` → action
  handlers, then `_process_ai_player_followup()` runs AI turns and call responses through the same
  handlers. `AIPlayerController` only decides (`get_turn_action`, `get_call_response`); every state
  change goes through `MahjongGameService`.
* Player type is a service-layer fact: `MahjongPlayer` has no AI flag, only
  `AIPlayerController.is_ai_player(seat)` knows. Names and AI flags go out once in `game_started`;
  later events use seats.
* Calls: a discard creates one `PendingCallPrompt` (`call_type=DISCARD`) holding every eligible
  caller, ron callers as `int` and meld callers as `MeldCaller`; a seat eligible for both is a ron
  caller only. Shouminkan creates a `CHANKAN` prompt. Each response removes the seat from
  `pending_seats`; when it is empty, `call_resolution.resolve_call_prompt()` picks ron > pon/kan >
  chi > pass. Dora reveal and riichi finalization after a discard wait until no ron is taken.
* Per-game side state lives in narrow trackers with a `cleanup_game()`: `FuritenTracker` (emits
  `FuritenEvent` on change) and `RoundAdvanceManager` (who still has to confirm the round end; AI
  seats are pre-confirmed).
* Errors: rule violations raise `GameRuleError` subclasses (`logic/exceptions.py`), never a bare
  `ValueError`, and handlers turn them into an `ErrorEvent`. A provably invalid action (data a real
  client could not send) raises `InvalidGameActionError` with the offending `seat`; `SessionManager`
  disconnects that seat (1008) and seats an AI player.
* Determinism: the same seed and inputs produce an identical replay trace. Randomness comes only
  from `rng.py` (PCG64DXSM, seeded per round); AI strategies must be deterministic for a given state.
  A change to wall or RNG behaviour bumps `RNG_VERSION`; a change to the replay format bumps
  `REPLAY_VERSION`.

## Sessions

* A game starts pending: `POST /games` registers a session per player, keyed by the player's game
  ticket string (the ticket is the session token for the whole game, never rotated). It starts when
  every expected human joins or the pending timeout fires, filling empty seats with AI; with no
  humans it is cancelled.
* Disconnect from a started game: an AI player takes the seat, the player's remaining bank time is
  saved, and any pending turn, call or round confirmation for that seat is resolved. When the last
  human leaves, the game is torn down, so there are never all-AI games.
* Reconnect: verify the ticket, find the disconnected session, then under the per-game lock evict
  stale connections, remove the AI player, send the `game_reconnected` snapshot, and re-send the
  draw if it is that player's turn (directly, not through the replay collector). Close evicted
  connections outside the lock.
* Timers (`TurnTimer` via `TimerManager`): each turn gets base time (5s), then a bank (20s start,
  +10s per round, 60s cap) that drains only past the base time. Meld-call and round-advance timers
  are fixed and never touch the bank.
* Game lifecycle rows (`GameRepository`) are best-effort: log a database failure, never let it block
  gameplay or socket cleanup.

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
  All must pass.
* REST bodies are read with `request.stream()` and a hard size cutoff, never `await request.body()`
  on untrusted input; handle `ClientDisconnect`.
* Validate the WebSocket `game_id` path parameter against `_GAME_ID_PATTERN` and
  `_MAX_GAME_ID_LENGTH` before accepting.
* Shutdown cancels every background task (`cancel_all_pending_timeouts()`,
  `cancel_all_auth_timeouts()`).
* Concealed hand tiles are logged at DEBUG only; game tickets and session tokens are never logged at
  INFO or above.

## Wire format

* Session messages use a string `type`; game events use an integer `t` from `wire/enums.py`, mapped
  through `EVENT_TYPE_INT`. Integer codes are stable: add new ones, never renumber.
* Event fields get short `serialization_alias` keys and are dumped with
  `by_alias=True, exclude_none=True`. Draw and discard pack into one integer (`messaging/compact.py`),
  melds into an IMME integer (`shared/lib/melds/`).
* A protocol change updates `docs/game-protocol.md` and the frontend schemas in
  `frontend/src/shared/protocol/` in the same change.

## Tests

* `tests/conftest.py` builders (`create_player`, `create_round_state`, `create_game_state`) and
  `tests/unit/helpers.py` (`_update_round_state`, `_update_player`) build frozen state.
* `MockConnection` and `MockGameService` (`tests/mocks/`) test routing and sessions without sockets;
  `tests/unit/session/helpers.py` (`create_started_game`, `disconnect_and_reconnect`) drives the
  session lifecycle; `tests/helpers/auth.py` (`make_test_game_ticket`) signs tickets;
  `tests/helpers/websocket.py` drives a `TestClient` WebSocket.
* Whole-game flows use the replay runner with fixtures in `tests/integration/replays/fixtures/` or a
  built `ReplayInput`, asserting on each step's `state_before` / `state_after`.
