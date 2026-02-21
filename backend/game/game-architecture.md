# Game Server Architecture

Game server handling real-time Mahjong gameplay via WebSocket.

**Port**: 8711

## REST API

- `GET /health` - Health check
- `GET /status` - Server status (`active_rooms`, `active_games`, `capacity_used`, `max_games`)
- `GET /rooms` - List all rooms (pre-game lobbies)
- `POST /rooms` - Create a room (called by lobby). Accepts `room_id` and optional `num_ai_players` field (0-3, defaults to 3)

## WebSocket API

### Connection

Connect to `ws://localhost:8711/ws/{room_id}` (room must be created first via lobby or `POST /rooms`). The same WebSocket connection is used for both the room phase and the game phase.

### Message Format

All messages use MessagePack binary format. Room/session messages use a string `"type"` field. Game events use an integer `"t"` field (see Game Events below). The server only accepts and sends binary WebSocket frames.

#### Client -> Server (Room Phase)

**Join Room** (requires HMAC-signed game ticket from the lobby server)
```json
{"type": "join_room", "room_id": "room123", "game_ticket": "<signed-ticket>"}
```

**Leave Room**
```json
{"type": "leave_room"}
```

**Set Ready**
```json
{"type": "set_ready", "ready": true}
```

#### Client -> Server (Game Phase)

**Game Action**
```json
{"type": "game_action", "action": "discard", "data": {"tile": "1m"}}
```

**Chat** (works in both room and game phase)
```json
{"type": "chat", "text": "Hello!"}
```

**Ping** (heartbeat keep-alive)
```json
{"type": "ping"}
```

**Reconnect** (rejoin an active game after disconnecting; uses the original game ticket for authentication)
```json
{"type": "reconnect", "room_id": "game123", "game_ticket": "<signed-ticket>"}
```

#### Server -> Client (Room Phase)

**Room Joined** (sent to the joining player with full room state)
```json
{"type": "room_joined", "room_id": "room123", "player_name": "Alice", "players": [{"name": "Alice", "ready": false}], "num_ai_players": 3}
```

**Room Left** (sent to the player who left)
```json
{"type": "room_left"}
```

**Player Joined/Left** (broadcast to other players in room)
```json
{"type": "player_joined", "player_name": "Charlie"}
{"type": "player_left", "player_name": "Charlie"}
```

**Player Ready Changed** (broadcast to all players in room)
```json
{"type": "player_ready_changed", "player_name": "Alice", "ready": true}
```

**Game Starting** (broadcast when all required players are ready, before game events)
```json
{"type": "game_starting"}
```

#### Server -> Client (Game Phase)

**Game Left** (sent to the player who left)
```json
{"type": "game_left"}
```

**Player Joined/Left** (broadcast to other players in game)
```json
{"type": "player_joined", "player_name": "Charlie"}
{"type": "player_left", "player_name": "Charlie"}
```

**Game Events** (sent as flat top-level messages, no wrapper envelope)

Game events use integer `"t"` keys for event types (0=meld, 1=draw, 2=discard, 3=call_prompt, 4=round_end, 5=riichi_declared, 6=dora_revealed, 7=error, 8=game_started, 9=round_started, 10=game_end, 11=furiten). All game event fields use compact Pydantic `serialization_alias` keys for wire compactness (e.g., `"s"` for seat, `"ws"` for winner_seat). Meld events use IMME integer encoding. Draw and discard events use packed integer encoding via `messaging/compact.py`.

```json
{"t": 8, "gid": "abc", "p": [{"s": 0, "nm": "Alice", "ai": 0}, ...], "dl": 0, "dd": [[1,2],[3,4]]}
{"t": 9, "s": 0, "w": "East", "n": 1, "dl": 0, "cp": 0, "di": [...], "h": 0, "r": 0, "mt": [...], "p": [{"s": 0, "sc": 25000}, ...], "dc": [3,4]}
{"t": 1, "d": 42}
{"t": 1, "d": 42, "aa": [{"a": "discard", "tl": [0,1,2]}]}
{"t": 2, "d": 597}
{"t": 0, "m": 12345}
{"t": 6, "ti": 42}
{"t": 3, "clt": "ron", "ti": 55, "frs": 2, "cs": 0}
{"t": 3, "clt": "meld", "ti": 55, "frs": 2, "cs": 0, "ac": [{"clt": "pon"}, {"clt": "chi", "opt": [[40, 44]]}]}
{"t": 4, "rt": 0, "ws": 0, "hr": {...}, "scs": {...}, "sch": {...}, ...}
{"t": 11, "f": true}
{"t": 10, "ws": 0, "st": [{"s": 0, "sc": 42300, "fs": 52}, ...]}
```

The `"m"` field in meld events is an IMME (Integer-Mapped Meld Encoding) value that losslessly encodes all meld fields (type, tiles, caller, from_seat) in a single 15-bit integer. See `shared/lib/melds/README.md` for encoding details. The `"d"` field in draw/discard events is a packed integer encoding seat and tile_id (draw: `d = seat * 136 + tile_id`) or seat, tile_id, tsumogiri, and riichi flags (discard: `d = flag * 544 + seat * 136 + tile_id`). See `messaging/compact.py` for encoding details.

Note: The `furiten` event is sent only to the affected player (target `seat_N`), not broadcast.

**Game Action: confirm_round** (sent after `round_end` to acknowledge round results)
```json
{"type": "game_action", "action": "confirm_round", "data": {}}
```

**Chat**
```json
{"type": "chat", "player_name": "Alice", "text": "Hello!"}
```

**Pong** (heartbeat response)
```json
{"type": "pong"}
```

**Game Reconnected** (sent to the reconnecting player with full game state snapshot, uses compact aliases)
```json
{"type": "game_reconnected", "gid": "game123", "s": 0, "p": [...], "w": "East", "n": 1, "cp": 0, "di": [...], "h": 0, "r": 0, "mt": [...], "dc": [3, 4], "tr": 70, "pst": [...], "dl": 0, "dd": [[1, 2], [3, 4]]}
```

**Player Reconnected** (broadcast to other players in game)
```json
{"type": "player_reconnected", "player_name": "Alice"}
```

**Error**
```json
{"type": "session_error", "code": "game_full", "message": "Game is full"}
```

Error codes:
- `already_in_game` - Player tried to join a room/game while already in one
- `already_in_room` - Player tried to join a room while already in one
- `room_not_found` - The requested room does not exist
- `room_full` - Room has reached its player capacity (4 - num_ai_players)
- `room_transitioning` - Room is currently transitioning to a game
- `name_taken` - Player name is already used in the room/game
- `not_in_room` - Player tried to perform a room action without being in a room
- `not_in_game` - Player tried to perform a game action without being in a game
- `game_not_started` - Player tried to perform a game action before the game started
- `invalid_message` - Message could not be parsed
- `action_failed` - Game action failed
- `reconnect_no_session` - No disconnected session found for the provided token
- `reconnect_no_seat` - Session has no seat assignment
- `reconnect_game_gone` - Game no longer exists (all players disconnected)
- `reconnect_game_mismatch` - Session token does not match the WebSocket path game ID
- `reconnect_retry_later` - Game is starting, retry shortly (transient)
- `reconnect_in_room` - Connection is currently in a room
- `reconnect_already_active` - Connection already in a game
- `reconnect_snapshot_failed` - Failed to build game state snapshot
- `invalid_ticket` - Game ticket is invalid or has a room_id mismatch

## Internal Architecture

Clean architecture pattern with clear separation between layers:

- **Transport Layer** (`server/`) - Starlette WebSocket + REST handling, environment-based server configuration
- **Application Layer** (`messaging/`, `session/`) - Message routing, event payload shaping, room/session management
- **Domain Layer** (`logic/`) - Riichi Mahjong game logic

### Protocol Abstraction

All message handling logic operates through `ConnectionProtocol`, an abstract interface that decouples business logic from the WebSocket transport. Messages are encoded/decoded using MessagePack binary format:

```
WebSocket (Starlette)
    │
    ▼
WebSocketConnection (implements ConnectionProtocol)
    │
    ▼
MessagePack encode/decode (encoder.py)
    │
    ▼
MessageRouter (pure Python, testable)
    │
    ▼
SessionManager (game/player management, delegates to RoomManager + SessionStore + TimerManager + HeartbeatMonitor, concurrency locks)
    │                                                       │
    ▼                                                       ▼
GameService (game logic interface)              EventPayload (wire serialization)
    → returns list[ServiceEvent]                    → service_event_payload()
    Methods: start_game, handle_action,             → shape_call_prompt_payload()
             get_player_seat, handle_timeout,
             replace_with_ai_player, restore_human_player,
             build_reconnection_snapshot,
             build_draw_event_for_seat,
             process_ai_player_actions_after_replacement
```

This enables:
- Unit tests without real sockets (using `MockConnection` from `tests/mocks/`)
- Integration tests with Starlette's `TestClient`
- Easy swapping of transport layers if needed

### Event System

The game service communicates through a typed event pipeline:

- **GameEvent** (Pydantic base, `game.logic.events`) - Domain events like DrawEvent (carries tile_id: int and available_actions), DiscardEvent, MeldEvent, DoraRevealedEvent, RoundEndEvent, FuritenEvent, GameStartedEvent, RoundStartedEvent, etc. All events use integer tile IDs only (no string representations). Event model fields use Pydantic `serialization_alias` for compact wire keys (e.g., `"s"` for seat, `"di"` for dora_indicators); `DrawEvent` and `DiscardEvent` fields are not aliased as they are packed into integers by `service_event_payload()`. Game start produces a two-phase sequence: `GameStartedEvent` (broadcast) followed by `RoundStartedEvent` (per-seat events with game view fields inlined at top level). After pon/chi, no DrawEvent is emitted — the client infers turn ownership from `MeldEvent.caller_seat`.
- **ServiceEvent** - Transport container wrapping a GameEvent with typed routing metadata (`BroadcastTarget` or `SeatTarget`). Events are serialized as flat top-level messages on the wire (no wrapper envelope). The `ReplayCollector` persists broadcast gameplay events and seat-targeted `DrawEvent` events (`available_actions` stripped); per-seat `RoundStartedEvent` views are merged into a single record with all players' tiles for full game reconstruction.
- **EventType** - StrEnum defining all event type identifiers internally; mapped to stable integer codes for wire serialization via `EVENT_TYPE_INT` in `event_payload.py`
- `convert_events()` transforms GameEvent lists into ServiceEvent lists; DISCARD prompts are split per-seat via `_split_discard_prompt_for_seat()` into RON or MELD wire events (ron-dominant: if a seat has both ron and meld eligibility, only a RON prompt is sent)
- `extract_round_result()` extracts round results from ServiceEvent lists

### Event Payload Shaping

`messaging/event_payload.py` centralizes the transformation of domain events into wire-format payloads, used by both `SessionManager` (for WebSocket broadcast) and `ReplayCollector` (for persistence):

- `service_event_payload()` converts a `ServiceEvent` into a wire-format dict, adding the event type as an integer `"t"` key (mapped via `EVENT_TYPE_INT`). `MeldEvent` is special-cased to produce a compact `{"t": 0, "m": <IMME_int>}` payload. `DrawEvent` and `DiscardEvent` are packed into a single integer `"d"` field via `encode_draw()`/`encode_discard()` from `messaging/compact.py`; draw events include `"aa"` (available actions) when present. All other events use Pydantic `serialization_alias` via `model_dump(by_alias=True, exclude_none=True)` for compact field names and automatic None-exclusion. `RoundEndEvent` is flattened: the nested result dict is inlined with `"rt"` for the result type
- `shape_call_prompt_payload()` transforms `CallPromptEvent` payloads (using compact alias keys) based on call type: for ron/chankan, drops the callers list (`"clr"`) and extracts `"cs"` (caller seat); for meld, builds an `"ac"` (available calls) list with per-caller options (`"clt"`, `"opt"`)

### Server Configuration

`server/settings.py` provides `GameServerSettings`, a Pydantic-settings model with `GAME_` environment prefix. Configurable fields: `max_capacity` (default 100), `log_dir`, `cors_origins` (parsed via custom `CorsEnvSettingsSource`), `replay_dir`, `room_ttl_seconds` (default 3600, min 60s — controls room TTL; expired rooms have their player connections closed by a background reaper task), `game_ticket_secret` (read from `AUTH_GAME_TICKET_SECRET` via validation alias), `database_path` (default `backend/storage.db`, read from `GAME_DATABASE_PATH` or `AUTH_DATABASE_PATH` via validation alias). Injected into the Starlette app via `create_app()`. The app registers startup/shutdown hooks to start/stop the room reaper background task. When the app creates its own `SessionManager`, it also creates and owns a `Database` instance (connected to `database_path`), injects a `SqliteGameRepository` into the session manager, and closes the database on shutdown. `SessionManager` accepts an optional `GameRepository` for persisting game lifecycle events: game starts (with player IDs and timestamp), completed games (`end_reason="completed"` after replay save), and abandoned games (`end_reason="abandoned"` when a started game is cleaned up because all players left). All database calls are best-effort — failures are logged but never block gameplay or socket cleanup.

### Room Model

`session/room.py` defines the pre-game lobby data structures:

- **Room** - Dataclass representing a lobby with `room_id`, `num_ai_players`, `host_connection_id`, `transitioning` flag (prevents new joins during room-to-game conversion), `players` dict, `settings: GameSettings`, and `created_at` (monotonic timestamp for TTL comparison). Properties: `players_needed`, `is_full`, `all_ready`, `get_player_info()`
- **RoomPlayer** - Dataclass for a player in the lobby with `connection`, `name`, `room_id`, `session_token`, `user_id`, and `ready` state
- **RoomPlayerInfo** - Pydantic model (in `messaging/types.py`) for room state messages with `name` and `ready` fields

### Game Logic Layer

The `logic/` module implements Riichi Mahjong rules:

- **MahjongService** - Unified orchestration entry point implementing GameService interface; dispatches both player and AI player actions through the same handler pipeline; manages AI player followup loop (`_process_ai_player_followup`, capped at `MAX_AI_PLAYER_TURN_ITERATIONS=100`) and AI player call response dispatch (`_dispatch_ai_player_call_responses`, capped at `MAX_AI_PLAYER_CALL_ITERATIONS=10`); delegates furiten state tracking to `FuritenTracker`; delegates round-advance confirmation tracking to `RoundAdvanceManager`; AI player tsumogiri fallback when an AI player's chosen action fails; auto-confirms pending round-advance after AI player replacement; returns `list[ServiceEvent]`
- **FuritenTracker** (`logic/furiten_tracker.py`) - Tracks per-seat furiten state and emits change events. Maintains a boolean per seat per game. After each action, compares effective furiten against the last known value, emitting `FuritenEvent` for any changes. Only checks during `PLAYING` phase. Follows the same pattern as `RoundAdvanceManager`: pure state tracking, no side effects, narrow API, `cleanup_game()` for teardown
- **RoundAdvanceManager** - Manages round advancement confirmation state (`PendingRoundAdvance`) for all games; tracks which player seats still need to confirm readiness between rounds; AI player seats are pre-confirmed at setup; provides `setup_pending()`, `confirm_seat()`, `is_pending()`, `get_unconfirmed_seats()`, `is_seat_required()`, and `cleanup_game()`
- **MahjongGame** - Manages game state across multiple rounds (hanchan); uma/oka end-game score adjustment with goshashonyu rounding (remainder ≤500 rounds toward zero, >500 rounds away); `init_game()` accepts optional `wall` parameter for deterministic testing; seed is a hex string; wall creation uses `dealer_seat` for dice-based wall breaking
- **Round** - Handles a single round with draws, discards, pending dora reveal, nagashi mangan detection, and keishiki tenpai with pure karaten exclusion; delegates wall operations (draw, dead wall replenishment, dora management) to `wall.py`
- **Turn** - Processes player actions and returns typed GameEvent objects
- **Actions** - Builds available actions as `AvailableActionItem` models (discardable tiles, riichi, tsumo, kan)
- **ActionHandlers** - Validates and processes player actions using typed Pydantic data models (DiscardActionData, RiichiActionData, etc.); call responses (pon, chi, ron, open kan) record intent on `PendingCallPrompt`; `_validate_caller_action_matches_prompt()` enforces per-caller action validity (ron callers can only CALL_RON on DISCARD prompts, meld callers validated against their available call types); `handle_pass` removes the caller from `pending_seats` and applies furiten (for DISCARD prompts, only ron callers receive furiten) without emitting any events; resolution triggers when all callers have responded or passed via `resolve_call_prompt()` from `call_resolution`; `_find_offending_seat_from_prompt()` uses resolution priority logic for blame attribution when call resolution fails
- **CallResolution** (`call_resolution.py`) - Resolves pending call prompts after all callers respond; picks winning response by priority (ron > pon/kan > chi > all pass); handles triple ron abortive draw, double/single ron, meld resolution, and chankan decline completion; for DISCARD prompts, `_finalize_discard_post_ron_check()` performs deferred dora reveal and riichi finalization after no ron, and `_resolve_all_passed_discard()` handles the all-passed case (dora/riichi already finalized, just advances turn)
- **Matchmaker** - Assigns players to randomized seats and fills remaining seats with AI players; supports 1-4 players based on `num_ai_players` setting; returns `list[SeatConfig]`
- **TurnTimer** - Server-side per-player bank time management with async timeout callbacks for turns, meld decisions, and round-advance confirmations; each player gets an independent timer instance; accepts optional `bank_seconds` constructor parameter for restoring preserved bank time on reconnection; `stop()` cancels timer and deducts bank time, while `consume_bank()` deducts without cancelling (for use inside timeout callbacks)
- **AIPlayerController** - Pure decision-maker for AI players using `dict[int, AIPlayer]` seat-to-AI-player mapping; provides `is_ai_player()`, `add_ai_player()`, `remove_ai_player()`, `get_turn_action()`, and `get_call_response()` without any orchestration or game state mutation; for DISCARD prompts, dispatches to ron or meld logic based on caller type (`int` = ron, `MeldCaller` = meld); supports runtime AI player addition for disconnect replacement
- **Enums** - String enum definitions: `GameAction` (includes `CONFIRM_ROUND`), `PlayerAction`, `MeldCallType`, `KanType`, `CallType` (RON, MELD, CHANKAN, DISCARD), `AbortiveDrawType`, `RoundResultType`, `WindName`, `MeldViewType`, `AIPlayerType`, `TimeoutType` (`TURN`, `MELD`, `ROUND_ADVANCE`); `MELD_CALL_PRIORITY` dict maps `MeldCallType` to resolution priority (kan > pon > chi)
- **Types** - Pydantic models for cross-component data: `SeatConfig`, `GamePlayerInfo` (player identity for game start broadcast), round results (`TsumoResult`, `RonResult`, `DoubleRonResult`, `ExhaustiveDrawResult`, `AbortiveDrawResult`, `NagashiManganResult`), action data models, player views (`GameView`, `PlayerView` with seat and score only, `dice` field), `PlayerStanding` (seat, score, final_score), `MeldCaller` (seat and call_type only, no server-internal fields), `AIPlayerAction`, `AvailableActionItem`, reconnection models (`DiscardInfo`, `PlayerReconnectState`, `ReconnectionSnapshot`); `RoundResult` union type
- **RNG** (`rng.py`) - Random number generation for wall shuffling; pure Python PCG64DXSM (Permuted Congruential Generator with DXSM output function); 768-bit cryptographic seed generation via `secrets.token_bytes`; hash-based per-round derivation with SHA512 domain separation; Fisher-Yates shuffle with rejection sampling; dice rolling; `RNG_VERSION` constant for replay compatibility; `generate_seed()`, `generate_shuffled_wall_and_dice()`, `create_seat_rng()`, `validate_seed_hex()`
- **Wall** (`wall.py`) - Frozen Pydantic `Wall` model encapsulating wall state (live wall, dead wall, dora indicators, pending dora count, dice values); `WallBreakInfo` model for computed break positions; dice-based wall breaking following standard Riichi Mahjong rules (68-stack ring model); `create_wall()`, `create_wall_from_tiles()`, `deal_initial_hands()`, `draw_tile()`, `draw_from_dead_wall()`, `add_dora_indicator()`, `reveal_pending_dora()`, `increment_pending_dora()`, `is_wall_exhausted()`, `tiles_remaining()`, `collect_ura_dora_indicators()`
- **Tiles** - 136-tile set with suits (man, pin, sou), honors (winds, dragons), and red fives; tile constants, 136-to-34 format conversion, terminal/honor checks, tile sorting, and hand-to-34-array conversion
- **Melds** - Detection of valid chi, pon, and kan combinations; kuikae restriction calculation; pao liability detection
- **Win** - Win detection, furiten checking (permanent, temporary, riichi furiten — riichi players get permanent furiten when their winning tile passes even if not eligible callers), renhou detection, chankan validation, and hand parsing
- **Scoring** - Score calculation (fu/han, point distribution for tsumo/ron); pao liability scoring (tsumo: liable pays full, ron: 50/50 split); nagashi mangan scoring (treated as a draw, does not clear riichi sticks); double yakuman scoring; returns typed result models
- **Riichi** - Riichi declaration validation and tenpai detection
- **Abortive** - Detection of abortive draws (kyuushu kyuuhai, suufon renda, etc.); returns `AbortiveDrawResult`
- **AIPlayer** - AI player for filling empty seats; returns `AIPlayerAction` model
- **Settings** (`settings.py`) - `GameSettings` Pydantic model with all configurable game rules; `validate_settings()` startup guard rejecting unsupported combinations; `GameType`/`EnchousenType`/`RenhouValue`/`LeftoverRiichiBets` enums; `build_optional_rules()` for scoring library integration; `get_wind_thresholds()` for wind-round boundary computation
- **State** - Frozen Pydantic game state models: `MahjongPlayer`, `MahjongRoundState`, `MahjongGameState`, `PendingCallPrompt`, `CallResponse`; all state is immutable (`frozen=True`); state updates use `model_copy(update={...})` pattern; `MahjongRoundState.wall` is a `Wall` object; `MahjongGameState.seed` is a hex string with `rng_version` field for replay compatibility; settings live only on `MahjongGameState`, not on `MahjongRoundState`; `MahjongPlayer.score` is required (no default)
- **MeldWrapper** (`meld_wrapper.py`) - `FrozenMeld` immutable wrapper for external `mahjong.meld.Meld` class; provides true immutability by storing meld data in frozen Pydantic model; converts to/from `Meld` at boundaries for library compatibility; `frozen_melds_to_melds()` utility for batch conversion
- **StateUtils** (`state_utils.py`) - Helper functions for immutable state updates: `update_player()`, `add_tile_to_player()`, `remove_tile_from_player()`, `add_discard_to_player()`, `advance_turn()`, `clear_pending_prompt()`, `add_prompt_response()`, `update_game_with_round()`, `update_all_discards()`, `clear_all_players_ippatsu()`
- **Exceptions** (`exceptions.py`) - Typed domain exception hierarchy rooted in `GameRuleError`; subclasses: `InvalidDiscardError`, `InvalidMeldError`, `InvalidRiichiError`, `InvalidWinError`, `InvalidActionError`, `UnsupportedSettingsError`. Domain modules raise these instead of raw `ValueError`. Action handlers catch `GameRuleError` and convert to `ErrorEvent`. Separately, `InvalidGameActionError` (not a `GameRuleError` subclass) is raised for provably invalid actions (fabricated data, modified client); caught by `SessionManager` to disconnect the offender (WebSocket close code 1008) and replace with an AI player. The broad `except Exception` containment in `MessageRouter` is preserved as a fatal safety net.
- **Utils** (`utils.py`) - Debug utility functions (`_hand_config_debug`, `_melds_debug`) for detailed error logging in scoring calculations; excluded from coverage

### Pending Call Prompt System

The game uses a unified call-response system where all players (player and AI player) respond to call opportunities through the same code path.

When a discard creates call opportunities, `process_discard_phase()` creates a single `PendingCallPrompt` with `call_type=DISCARD` containing all eligible callers (both ron and meld) in one prompt. Ron-dominant policy ensures dual-eligible seats (can both ron and meld the same tile) only appear as ron callers. For chankan opportunities, `_process_added_kan_call()` creates a `CHANKAN` prompt.

The `PendingCallPrompt` on `MahjongRoundState` contains:
- `call_type` - the type of call opportunity (DISCARD or CHANKAN; callers list uses `int` for ron callers and `MeldCaller` for meld callers)
- `tile_id` - the tile being called on
- `from_seat` - the seat that discarded or played the tile
- `pending_seats` - set of seats that have not yet responded
- `callers` - the original eligible callers list (`list[int | MeldCaller]`)
- `responses` - collected `CallResponse` objects

When a DISCARD prompt is created, dora reveal and riichi finalization are deferred until resolution (after the ron check passes). This ensures dora is not revealed if someone calls ron.

Each caller responds through the standard action handlers (`handle_pass`, `handle_pon`, `handle_chi`, `handle_ron`, `handle_kan`). These handlers record the response and remove the caller from `pending_seats`. When `pending_seats` is empty, `resolve_call_prompt()` (in `call_resolution.py`) picks the winner by priority (ron > pon/kan > chi > all pass) and executes the action.

This eliminates the previous duplication where AI player and player call responses had separate orchestration paths.

### Unified Turn Loop

`MahjongGameService` orchestrates all turns through a single dispatch pipeline:

1. Player actions enter via `handle_action()` -> `_dispatch_and_process()` -> action handlers
2. After each player action, `_process_ai_player_followup()` iterates AI player turns through the same `_dispatch_and_process()` path
3. AI player call responses are dispatched through `_dispatch_ai_player_call_responses()` -> `_dispatch_action()` -> same action handlers

`AIPlayerController` is a pure decision-maker: `get_turn_action()` returns action data for an AI player's turn, `get_call_response()` returns the AI player's response to a call prompt. Neither method modifies game state or calls handlers directly. All state mutation flows through `MahjongGameService`.

### Room-Based Game Creation

Rooms use a `num_ai_players` parameter (0-3) instead of separate game modes. The `num_ai_players` value determines how many players are needed: `num_players_needed = 4 - num_ai_players`.

- `num_ai_players=3` (default): game starts when 1 player joins and readies up (1 player + 3 AI players)
- `num_ai_players=0`: game starts when 4 players all ready up (pure PvP)
- `num_ai_players=1` or `num_ai_players=2`: game starts when the required players all ready up, remaining seats filled with AI players

The `num_ai_players` is set at room creation time via `POST /rooms` and stored on the `Room` dataclass. Players join a room, toggle ready, and the game starts when all required players are ready. The room transitions to a `Game` via `RoomManager._transition_room_to_game()`, which delegates back to `SessionManager._handle_room_transition()` via callback.

### Disconnect-to-AI-Player Replacement

When a player disconnects from a started game (either by closing the connection or by sending a provably invalid game action):
1. The player's connection is closed (code 1008 for invalid actions, normal close for voluntary disconnect)
2. The player is removed from the session layer (`game.players`)
3. If other players remain, `replace_with_ai_player()` registers an AI player at the disconnected player's seat
4. The disconnected player's timer is stopped (elapsed turn time deducted from bank) and remaining bank seconds are saved to the session for reconnection
5. `process_ai_player_actions_after_replacement()` handles any pending turn, call prompt, or round-advance confirmation for the replaced seat
6. If the last player disconnects, the game is cleaned up (no all-AI-player games)

### Reconnection

When a disconnected player reconnects:
1. The game ticket is HMAC-verified by the router (signature, expiry, room binding)
2. The session is looked up by the game ticket string (must be disconnected, must match the game ID from the WebSocket path)
3. Guard checks prevent reconnection if the connection is already in a room or game
4. Under the per-game lock, stale connections at the seat are evicted
5. The AI player at the seat is removed via `restore_human_player()`
6. A `ReconnectionSnapshot` is built containing the full game state for the player's seat
7. The player is registered in the session layer with a timer initialized from saved bank seconds
8. The `game_reconnected` message with the full snapshot is sent to the reconnecting player
9. A `player_reconnected` message is broadcast to other players
10. If it is the reconnected player's turn (no pending call prompt or round advance), the draw event is re-sent directly (bypassing replay collector to avoid duplicates)
11. Stale connections are closed outside the lock

Reconnection is not possible after all human players disconnect (the game is canceled immediately).

For invalid game actions, the `InvalidGameActionError` exception carries a `seat` attribute for blame attribution: when a resolution-time error is caused by a different player's prior bad data, the offending seat (not the action requester) is disconnected.

### Authentication & Session Identity

**Game Ticket Authentication**: Players authenticate via HMAC-SHA256 signed game tickets issued by the lobby server. The `MessageRouter` verifies the ticket signature and expiry using `shared.auth.game_ticket.verify_game_ticket()` for both `join_room` and `reconnect` messages. Tickets have a 24-hour TTL (matching the lobby session). The ticket contains `user_id`, `username`, `room_id`, `issued_at`, and `expires_at`. The router rejects invalid, expired, or room-mismatched tickets with `INVALID_TICKET` error. On success, the router extracts `username` and `user_id` from the verified ticket and passes them to `SessionManager.join_room()`. The ticket secret is shared between the lobby and game servers via the `AUTH_GAME_TICKET_SECRET` environment variable.

**Game Ticket as Session Token**: The game ticket string serves as the session identifier for the entire game lifecycle, including reconnection. When a player joins a room, the router passes the game ticket string as the `session_token` to the session layer. On reconnect, the client sends the same game ticket; the router verifies the HMAC signature, then the session manager looks up the session by the ticket string. There is no token rotation — the same ticket is used throughout.

Session lifecycle:
- **Created**: When a player joins a room (session token = game ticket string)
- **Seat bound**: When the game starts, the player's seat is recorded on the session
- **Marked disconnected**: When a player disconnects from a started game (timestamp recorded)
- **Removed**: When a player leaves before the game starts, or on defensive cleanup
- **Cleaned up**: When a game ends and is empty, all sessions for that game are removed

Session data (`SessionData`) stores: session token (game ticket string), player name, game ID, user_id (from verified game ticket), seat number, disconnect timestamp, and remaining bank seconds. Sessions are in-memory only (no persistence). On reconnection, the game ticket is HMAC-verified by the router, then the session is looked up by the ticket string, the AI player at the seat is removed, and the human player is restored. Bank time is preserved across disconnect/reconnect cycles. `SessionStore` provides `get_session()` (lookup by token) and `mark_reconnected()` (clears disconnect state) for reconnection support.

### Per-Player Timers

Each player gets an independent `TurnTimer` instance, managed by `TimerManager` (`session/timer_manager.py`). `SessionManager` delegates all timer operations to `TimerManager` and provides a timeout callback.

Timer behavior:
- On round start, round bonus is added to all player timers
- On turn start (draw or pon/chi meld), the current seat's timer starts counting bank time
- On call prompt, meld timers start for all connected callers (PvP can have multiple simultaneous callers)
- On round end, fixed-duration round-advance timers start for all players; when a player confirms (or the timer expires), they are marked as ready; once all players confirm, the next round begins
- When a player acts, their timer stops (bank time deducted) and other callers' meld timers are cancelled (no bank time deducted)
- On game end, all player timers are cleaned up

### AI Player Identity Separation

The game logic layer (`MahjongPlayer`, `MahjongRoundState`) has no knowledge of player types. `MahjongPlayer` has no `is_ai_player` field.

AI player identity is managed exclusively by `AIPlayerController.is_ai_player(seat)` at the service layer. Player names and AI status are sent once in the `game_started` event via `GamePlayerInfo`. Subsequent events (`round_started`, `game_end`) identify players by seat number only — `PlayerView` carries `(seat, score)` and `PlayerStanding` carries `(seat, score, final_score)`.

### Replay System

The replay adapter (`backend/game/replay/`) enables deterministic replay of game sessions through `MahjongGameService`'s public API.

- **ReplayInput** defines a versioned input format: a hex string seed with `rng_version`, 4 player names, an ordered sequence of player actions, and an optional `wall` (pre-arranged tile order for testing)
- **ReplayTrace** captures full output: startup events, per-step state transitions (`state_before`/`state_after`), and final state; rejects replays with missing or mismatched `rng_version`
- **run_replay()** / **run_replay_async()** feed recorded actions through the service and return a trace; support `auto_confirm_rounds` (injects synthetic `CONFIRM_ROUND` steps) and `auto_pass_calls` (injects synthetic `PASS` steps for pending call prompts)
- **ReplayServiceProtocol** is the replay-facing protocol boundary; default factory uses `MahjongGameService(auto_cleanup=False)`
- **ReplayLoader** (`loader.py`) parses JSON Lines files (produced by `ReplayCollector`) back into `ReplayInput`; reconstructs original player name input order from the seed via RNG reconstruction; dispatches events by integer `"t"` key; decodes compact meld events via IMME `decode_meld_compact()`; decodes draw/discard events via packed integer decoding (`decode_draw`/`decode_discard` from `messaging/compact.py`); all replay keys use compact aliases (e.g., `"sd"` for seed, `"rv"` for rng_version, `"p"` for players, `"s"` for seat, `"nm"` for name); maps event types to game actions (discard, meld, ron, tsumo, etc.)
- **Replay format version**: `REPLAY_VERSION` constant in `models.py` (currently `"0.3-dev"`); loader validates version compatibility
- **Determinism contract**: same seed + same input events = identical trace; AI player strategies must be deterministic given the same state
- **Dependency direction**: `game.replay` imports from `game.logic`; game logic modules never import from `game.replay` (enforced by AST-based integration test)
- `start_game()` accepts an optional hex string `seed` parameter for deterministic game creation; when omitted, a cryptographic hex seed is generated via `rng.generate_seed()`

## Project Structure

```
ronin/
├── pyproject.toml
├── Makefile
└── backend/
    ├── shared/
    │   ├── dal/
    │   │   ├── __init__.py           # Public API: PlayerRepository, GameRepository, PlayedGame
    │   │   ├── models.py             # PlayedGame persistence model
    │   │   ├── player_repository.py  # Abstract PlayerRepository interface
    │   │   └── game_repository.py    # Abstract GameRepository interface
    │   ├── db/
    │   │   ├── __init__.py           # Public API: Database, SqlitePlayerRepository, SqliteGameRepository
    │   │   ├── connection.py         # Database wrapper (SQLite connection, schema, migration)
    │   │   ├── player_repository.py  # SQLite PlayerRepository implementation
    │   │   └── game_repository.py    # SQLite GameRepository implementation
    │   └── lib/
    │       └── melds/
    │           ├── __init__.py     # Public API re-exports
    │           ├── compact.py      # IMME encoder/decoder (zero external deps)
    │           ├── fixtures.py     # Test fixture builder for all meld types
    │           ├── serializers.py  # Format comparison (JSON, msgpack, compact)
    │           └── README.md       # IMME encoding documentation
    └── game/
        ├── server/
        │   ├── app.py          # Starlette app factory
        │   ├── settings.py     # GameServerSettings (env-based config via pydantic-settings)
        │   ├── types.py        # REST API types
        │   └── websocket.py    # WebSocket endpoint
        ├── messaging/
        │   ├── protocol.py     # ConnectionProtocol interface
        │   ├── types.py        # Message schemas (Pydantic)
        │   ├── compact.py      # Packed integer encoding for draw/discard events
        │   ├── encoder.py      # MessagePack encoding/decoding
        │   ├── event_payload.py # Event payload shaping for wire and replay serialization
        │   └── router.py       # Message routing
        ├── session/
        │   ├── models.py        # Player, Game, SessionData dataclasses
        │   ├── room.py          # Room, RoomPlayer for pre-game lobby
        │   ├── types.py         # Pydantic models (RoomInfo for lobby listing)
        │   ├── manager.py       # Session/game management
        │   ├── room_manager.py  # Room lifecycle management (creation, join/leave, readiness, TTL expiration)
        │   ├── broadcast.py     # Shared broadcast utility for sending messages to player groups
        │   ├── session_store.py # In-memory session identity persistence
        │   ├── replay_collector.py # Collects broadcast events and merges per-seat round_started views for post-game persistence
        │   ├── timer_manager.py # Per-player turn timer lifecycle
        │   └── heartbeat.py     # Client liveness heartbeat monitor
        ├── replay/
        │   ├── __init__.py      # Public API re-exports
        │   ├── models.py        # ReplayInput, ReplayTrace, ReplayStep, error types
        │   ├── runner.py        # ReplayServiceProtocol, run_replay/run_replay_async
        │   └── loader.py        # Parse JSON Lines replay files into ReplayInput
        ├── logic/
        │   ├── service.py          # GameService interface
        │   ├── mahjong_service.py  # MahjongService orchestration
        │   ├── game.py             # MahjongGame state management
        │   ├── round.py            # Round management
        │   ├── turn.py             # Turn processing, returns typed events
        │   ├── actions.py          # Available actions builder
        │   ├── action_handlers.py  # Action validation and processing
        │   ├── action_result.py    # Shared ActionResult NamedTuple and helpers
        │   ├── call_resolution.py  # Call resolution subsystem (ron/meld/pass)
        │   ├── events.py           # Domain event models, ServiceEvent, convert_events()
        │   ├── exceptions.py       # Typed domain exceptions (GameRuleError hierarchy)
        │   ├── round_advance.py    # Round advancement confirmation state machine
        │   ├── furiten_tracker.py  # Per-player furiten state change tracking and event emission
        │   ├── ai_player_controller.py # AI player turn and call handling
        │   ├── enums.py            # String enum definitions for game concepts
        │   ├── types.py            # Pydantic models for cross-component data
        │   ├── rng.py              # PCG64DXSM RNG, seed generation, Fisher-Yates shuffle, dice rolling
        │   ├── wall.py             # Wall state model and all wall operations (create, deal, draw, dora)
        │   ├── tiles.py            # Tile constants, format conversion, sorting
        │   ├── melds.py            # Meld detection (chi, pon, kan)
        │   ├── win.py              # Win detection and hand parsing
        │   ├── scoring.py          # Score calculation and distribution
        │   ├── riichi.py           # Riichi declaration logic
        │   ├── abortive.py         # Abortive draw detection
        │   ├── state.py            # Game state dataclasses
        │   ├── state_utils.py      # Pure functions for immutable state updates
        │   ├── meld_compact.py     # Bridge: FrozenMeld/MeldEvent -> IMME compact encoding
        │   ├── meld_wrapper.py     # FrozenMeld immutable wrapper for external Meld class
        │   ├── settings.py         # GameSettings Pydantic model with configurable rules
        │   ├── ai_player.py         # AI player logic
        │   ├── matchmaker.py       # Seat assignment and AI player filling
        │   ├── timer.py            # Turn timer with bank time management
        │   └── utils.py            # Debug utility functions for scoring diagnostics
        └── tests/
            ├── mocks/              # MockConnection, MockGameService
            ├── unit/
            └── integration/
```

### Test Infrastructure (`tests/mocks/`, `tests/conftest.py`)

- **MockConnection** (`tests/mocks/connection.py`) - Implements `ConnectionProtocol` with `asyncio.Queue` inbox and list outbox; provides `simulate_receive()` for injecting client messages and `sent_messages` for assertions
- **MockGameService** (`tests/mocks/game_service.py`) - Implements `GameService` interface; echoes actions as broadcast events; creates mock seat assignments on `start_game()`
- **State builders** (`tests/conftest.py`) - Factory functions `create_player()`, `create_round_state()`, `create_game_state()` for constructing frozen Pydantic state objects with sensible defaults, avoiding boilerplate in every test
- **Copy-on-write helpers** (`tests/unit/helpers.py`) - `_update_round_state()` and `_update_player()` for modifying frozen state in test setup via `model_copy(update={...})`
- **Session helpers** (`tests/unit/session/helpers.py`) - `create_started_game()` orchestrates full room lifecycle (create/join/ready/start) for session tests; `disconnect_and_reconnect()` simulates disconnect and reconnection for reconnection tests
- **Auth helpers** (`tests/helpers/auth.py`) - `make_test_game_ticket()` creates HMAC-signed game tickets for test use; `TEST_TICKET_SECRET` is the shared secret used by test fixtures

### Unit Tests (No Sockets)

Use `MockConnection` to test message handling:

```python
async def test_join_room():
    connection = MockConnection()
    router.handle_connect(connection)

    session_manager.create_room("room1", num_ai_players=3)
    ticket = make_test_game_ticket("Alice", "room1")
    await router.handle_message(connection, {
        "type": "join_room",
        "room_id": "room1",
        "game_ticket": ticket,
    })

    response = connection.sent_messages[0]
    assert response["type"] == "room_joined"
```

### Integration Tests (With TestClient)

Use Starlette's `TestClient` for full WebSocket flow with MessagePack:

```python
import msgpack

def test_websocket():
    client = TestClient(app)
    client.post("/rooms", json={"room_id": "test_room"})
    with client.websocket_connect("/ws/test_room") as ws:
        ticket = make_test_game_ticket("Alice", "test_room")
        ws.send_bytes(msgpack.packb({"type": "join_room", "room_id": "test_room", "game_ticket": ticket}))
        response = msgpack.unpackb(ws.receive_bytes())
        assert response["type"] == "room_joined"
```

### Replay-Based Integration Tests

Deterministic game flow testing using the replay system with fixture files (`tests/integration/replays/fixtures/`) or programmatic `ReplayInput` construction. The replay trace enables precise state-transition assertions on `state_before`/`state_after` for each step.

### Architecture Boundary Tests

AST-based static analysis (`tests/integration/test_architecture_boundary.py`) enforces layer boundary rules: (1) `game.logic` must not import from `game.replay`, (2) `game.messaging` must not import from `game.session`. Only runtime imports are checked; `TYPE_CHECKING` imports are excluded.
