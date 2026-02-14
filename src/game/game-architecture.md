# Game Server Architecture

Game server handling real-time Mahjong gameplay via WebSocket.

**Port**: 8001

## REST API

- `GET /health` - Health check
- `GET /status` - Server status (`active_rooms`, `active_games`, `capacity_used`, `max_games`)
- `GET /rooms` - List all rooms (pre-game lobbies)
- `POST /rooms` - Create a room (called by lobby). Accepts `room_id` and optional `num_ai_players` field (0-3, defaults to 3)

## WebSocket API

### Connection

Connect to `ws://localhost:8001/ws/{room_id}` (room must be created first via lobby or `POST /rooms`). The same WebSocket connection is used for both the room phase and the game phase.

### Message Format

All messages use MessagePack binary format with a `type` field. The server only accepts and sends binary WebSocket frames.

#### Client -> Server (Room Phase)

**Join Room**
```json
{"type": "join_room", "room_id": "room123", "player_name": "Alice"}
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

#### Server -> Client (Room Phase)

**Room Joined** (sent to the joining player with full room state)
```json
{"type": "room_joined", "room_id": "room123", "players": [{"name": "Alice", "ready": false}], "num_ai_players": 3}
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
```json
{"type": "game_started", "players": [{"seat": 0, "name": "Alice", "is_ai_player": false}, ...]}
{"type": "round_started", "view": {"seat": 0, "round_wind": "East", ...}}
{"type": "draw", "seat": 0, "tile_id": 42, "available_actions": [...]}
{"type": "discard", "seat": 2, "tile_id": 55, "is_tsumogiri": true, "is_riichi": false}
{"type": "meld", "meld_type": "pon", "caller_seat": 1, "tile_ids": [8, 9, 10], "from_seat": 0, "called_tile_id": 10}
{"type": "dora_revealed", "tile_id": 42}
{"type": "call_prompt", "call_type": "ron", "tile_id": 55, "from_seat": 2, "caller_seat": 0}
{"type": "call_prompt", "call_type": "meld", "tile_id": 55, "from_seat": 2, "caller_seat": 0, "available_calls": [{"call_type": "pon"}, {"call_type": "chi", "options": [[40, 44]]}]}
{"type": "round_end", "result": {...}}
{"type": "furiten", "is_furiten": true}
{"type": "game_end", "result": {...}}
```

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
SessionManager (game/player management, delegates to SessionStore + TimerManager + HeartbeatMonitor, concurrency locks)
    │                                                       │
    ▼                                                       ▼
GameService (game logic interface)              EventPayload (wire serialization)
    → returns list[ServiceEvent]                    → service_event_payload()
    Methods: start_game, handle_action,             → shape_call_prompt_payload()
             get_player_seat, handle_timeout,
             replace_with_ai_player,
             process_ai_player_actions_after_replacement
```

This enables:
- Unit tests without real sockets (using `MockConnection` from `tests/mocks/`)
- Integration tests with Starlette's `TestClient`
- Easy swapping of transport layers if needed

### Event System

The game service communicates through a typed event pipeline:

- **GameEvent** (Pydantic base, `game.logic.events`) - Domain events like DrawEvent (carries tile_id and available_actions), DiscardEvent, MeldEvent, DoraRevealedEvent, RoundEndEvent, FuritenEvent, GameStartedEvent, RoundStartedEvent, etc. All events use integer tile IDs only (no string representations). Game start produces a two-phase sequence: `GameStartedEvent` (broadcast) followed by `RoundStartedEvent` (per-seat events with full GameView).
- **ServiceEvent** - Transport container wrapping a GameEvent with typed routing metadata (`BroadcastTarget` or `SeatTarget`). Events are serialized as flat top-level messages on the wire (no wrapper envelope). The `ReplayCollector` persists broadcast gameplay events and seat-targeted `DrawEvent` events (null `tile_id` draws excluded, `available_actions` stripped); per-seat `RoundStartedEvent` views are merged into a single record with all players' tiles for full game reconstruction.
- **EventType** - String enum defining all event type identifiers
- `convert_events()` transforms GameEvent lists into ServiceEvent lists; DISCARD prompts are split per-seat via `_split_discard_prompt_for_seat()` into RON or MELD wire events (ron-dominant: if a seat has both ron and meld eligibility, only a RON prompt is sent)
- `extract_round_result()` extracts round results from ServiceEvent lists

### Event Payload Shaping

`messaging/event_payload.py` centralizes the transformation of domain events into wire-format payloads, used by both `SessionManager` (for WebSocket broadcast) and `ReplayCollector` (for persistence):

- `service_event_payload()` converts a `ServiceEvent` into a wire-format dict, stripping internal `type` and `target` fields and adding the event type string as `"type"`
- `shape_call_prompt_payload()` transforms `CallPromptEvent` payloads based on call type: for ron/chankan, drops the callers list and extracts `caller_seat`; for meld, builds an `available_calls` list with per-caller options

### Server Configuration

`server/settings.py` provides `GameServerSettings`, a Pydantic-settings model with `GAME_` environment prefix. Configurable fields: `max_games` (default 100), `log_dir`, `cors_origins` (parsed via custom `CorsEnvSettingsSource`), `replay_dir`. Injected into the Starlette app via `create_app()`.

### Room Model

`session/room.py` defines the pre-game lobby data structures:

- **Room** - Dataclass representing a lobby with `room_id`, `num_ai_players`, `host_connection_id`, `transitioning` flag (prevents new joins during room-to-game conversion), `players` dict, and `settings: GameSettings`. Properties: `players_needed`, `is_full`, `all_ready`, `get_player_info()`
- **RoomPlayer** - Dataclass for a player in the lobby with `connection`, `name`, `room_id`, `session_token`, and `ready` state
- **RoomPlayerInfo** - Pydantic model for room state messages with `name` and `ready` fields

### Game Logic Layer

The `logic/` module implements Riichi Mahjong rules:

- **MahjongService** - Unified orchestration entry point implementing GameService interface; dispatches both player and AI player actions through the same handler pipeline; manages AI player followup loop (`_process_ai_player_followup`, capped at `MAX_AI_PLAYER_TURN_ITERATIONS=100`) and AI player call response dispatch (`_dispatch_ai_player_call_responses`, capped at `MAX_AI_PLAYER_CALL_ITERATIONS=10`); tracks per-player furiten state and emits `FuritenEvent` on state transitions; delegates round-advance confirmation tracking to `RoundAdvanceManager`; AI player tsumogiri fallback when an AI player's chosen action fails; auto-confirms pending round-advance after AI player replacement; returns `list[ServiceEvent]`
- **RoundAdvanceManager** - Manages round advancement confirmation state (`PendingRoundAdvance`) for all games; tracks which player seats still need to confirm readiness between rounds; AI player seats are pre-confirmed at setup; provides `setup_pending()`, `confirm_seat()`, `is_pending()`, `get_unconfirmed_seats()`, `is_seat_required()`, and `cleanup_game()`
- **MahjongGame** - Manages game state across multiple rounds (hanchan); uma/oka end-game score adjustment with goshashonyu rounding (remainder ≤500 rounds toward zero, >500 rounds away); `init_game()` accepts optional `wall` parameter for deterministic testing
- **Round** - Handles a single round with wall, draws, discards, dead wall replenishment, pending dora reveal, nagashi mangan detection, and keishiki tenpai with pure karaten exclusion
- **Turn** - Processes player actions and returns typed GameEvent objects
- **Actions** - Builds available actions as `AvailableActionItem` models (discardable tiles, riichi, tsumo, kan)
- **ActionHandlers** - Validates and processes player actions using typed Pydantic data models (DiscardActionData, RiichiActionData, etc.); call responses (pon, chi, ron, open kan) record intent on `PendingCallPrompt`; `_validate_caller_action_matches_prompt()` enforces per-caller action validity (ron callers can only CALL_RON on DISCARD prompts, meld callers validated against their available call types); `handle_pass` removes the caller from `pending_seats` and applies furiten (for DISCARD prompts, only ron callers receive furiten) without emitting any events; resolution triggers when all callers have responded or passed via `resolve_call_prompt()` from `call_resolution`; `_find_offending_seat_from_prompt()` uses resolution priority logic for blame attribution when call resolution fails
- **CallResolution** (`call_resolution.py`) - Resolves pending call prompts after all callers respond; picks winning response by priority (ron > pon/kan > chi > all pass); handles triple ron abortive draw, double/single ron, meld resolution, and chankan decline completion; for DISCARD prompts, `_finalize_discard_post_ron_check()` performs deferred dora reveal and riichi finalization after no ron, and `_resolve_all_passed_discard()` handles the all-passed case (dora/riichi already finalized, just advances turn)
- **Matchmaker** - Assigns players to randomized seats and fills remaining seats with AI players; supports 1-4 players based on `num_ai_players` setting; returns `list[SeatConfig]`
- **TurnTimer** - Server-side per-player bank time management with async timeout callbacks for turns, meld decisions, and round-advance confirmations; each player gets an independent timer instance; `stop()` cancels timer and deducts bank time, while `consume_bank()` deducts without cancelling (for use inside timeout callbacks)
- **AIPlayerController** - Pure decision-maker for AI players using `dict[int, AIPlayer]` seat-to-AI-player mapping; provides `is_ai_player()`, `add_ai_player()`, `get_turn_action()`, and `get_call_response()` without any orchestration or game state mutation; for DISCARD prompts, dispatches to ron or meld logic based on caller type (`int` = ron, `MeldCaller` = meld); supports runtime AI player addition for disconnect replacement
- **Enums** - String enum definitions: `GameAction` (includes `CONFIRM_ROUND`), `PlayerAction`, `MeldCallType`, `KanType`, `CallType` (RON, MELD, CHANKAN, DISCARD), `AbortiveDrawType`, `RoundResultType`, `WindName`, `MeldViewType`, `AIPlayerType`, `TimeoutType` (`TURN`, `MELD`, `ROUND_ADVANCE`); `MELD_CALL_PRIORITY` dict maps `MeldCallType` to resolution priority (kan > pon > chi)
- **Types** - Pydantic models for cross-component data: `SeatConfig`, `GamePlayerInfo` (player identity for game start broadcast), round results (`TsumoResult`, `RonResult`, `DoubleRonResult`, `ExhaustiveDrawResult`, `AbortiveDrawResult`, `NagashiManganResult`), action data models, player views (`GameView`, `PlayerView`), `MeldCaller` (seat and call_type only, no server-internal fields), `AIPlayerAction`, `AvailableActionItem`; `RoundResult` union type
- **Tiles** - 136-tile set with suits (man, pin, sou), honors (winds, dragons), and red fives; wall generation uses seeded `random.Random(seed + round_number)` with a double-shuffle algorithm (two passes of swap-based shuffling) for determinism
- **Melds** - Detection of valid chi, pon, and kan combinations; kuikae restriction calculation; pao liability detection
- **Win** - Win detection, furiten checking (permanent, temporary, riichi furiten — riichi players get permanent furiten when their winning tile passes even if not eligible callers), renhou detection, chankan validation, and hand parsing
- **Scoring** - Score calculation (fu/han, point distribution for tsumo/ron); pao liability scoring (tsumo: liable pays full, ron: 50/50 split); nagashi mangan scoring (treated as a draw, does not clear riichi sticks); double yakuman scoring; returns typed result models
- **Riichi** - Riichi declaration validation and tenpai detection
- **Abortive** - Detection of abortive draws (kyuushu kyuuhai, suufon renda, etc.); returns `AbortiveDrawResult`
- **AIPlayer** - AI player for filling empty seats; returns `AIPlayerAction` model
- **Settings** (`settings.py`) - `GameSettings` Pydantic model with all configurable game rules; `validate_settings()` startup guard rejecting unsupported combinations; `GameType`/`EnchousenType`/`RenhouValue`/`LeftoverRiichiBets` enums; `build_optional_rules()` for scoring library integration; `get_wind_thresholds()` for wind-round boundary computation
- **State** - Frozen Pydantic game state models: `MahjongPlayer`, `MahjongRoundState`, `MahjongGameState`, `PendingCallPrompt`, `CallResponse`; all state is immutable (`frozen=True`); state updates use `model_copy(update={...})` pattern; settings live only on `MahjongGameState`, not on `MahjongRoundState`; `MahjongPlayer.score` is required (no default)
- **MeldWrapper** (`meld_wrapper.py`) - `FrozenMeld` immutable wrapper for external `mahjong.meld.Meld` class; provides true immutability by storing meld data in frozen Pydantic model; converts to/from `Meld` at boundaries for library compatibility; `frozen_melds_to_melds()` utility for batch conversion
- **StateUtils** (`state_utils.py`) - Helper functions for immutable state updates: `update_player()`, `add_tile_to_player()`, `remove_tile_from_player()`, `add_discard()`, `add_meld()`, `reveal_dora()`, `advance_turn()`, etc.
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

The `num_ai_players` is set at room creation time via `POST /rooms` and stored on the `Room` dataclass. Players join a room, toggle ready, and the game starts when all required players are ready. The room transitions to a `Game` via `SessionManager._transition_room_to_game()`.

### Disconnect-to-AI-Player Replacement

When a player disconnects from a started game (either by closing the connection or by sending a provably invalid game action):
1. The player's connection is closed (code 1008 for invalid actions, normal close for voluntary disconnect)
2. The player is removed from the session layer (`game.players`)
3. If other players remain, `replace_with_ai_player()` registers an AI player at the disconnected player's seat
4. The disconnected player's timer is cancelled
5. `process_ai_player_actions_after_replacement()` handles any pending turn, call prompt, or round-advance confirmation for the replaced seat
6. If the last player disconnects, the game is cleaned up (no all-AI-player games)

For invalid game actions, the `InvalidGameActionError` exception carries a `seat` attribute for blame attribution: when a resolution-time error is caused by a different player's prior bad data, the offending seat (not the action requester) is disconnected.

### Session Identity

Sessions are created server-side during the room-to-game transition. When all required players in a room are ready, the server generates a `session_token` (UUID) for each player, creates sessions in `SessionStore`, and transitions the room into a game — all on the same WebSocket connection. The token is managed server-side for reconnection support.

Session lifecycle:
- **Created**: When the room transitions to a game (server generates tokens for all players)
- **Seat bound**: When the game starts, the player's seat is recorded on the session
- **Marked disconnected**: When a player disconnects from a started game (timestamp recorded)
- **Removed**: When a player leaves before the game starts, or on defensive cleanup
- **Cleaned up**: When a game ends and is empty, all sessions for that game are removed

Session data (`SessionData`) stores: session token, player name, game ID, seat number, and disconnect timestamp. Sessions are in-memory only (no persistence). Reconnection logic (rebinding a new WebSocket to an existing session) is not yet implemented.

### Per-Player Timers

Each player gets an independent `TurnTimer` instance, managed by `TimerManager` (`session/timer_manager.py`). `SessionManager` delegates all timer operations to `TimerManager` and provides a timeout callback.

Timer behavior:
- On round start, round bonus is added to all player timers
- On turn start, the current seat's timer starts counting bank time
- On call prompt, meld timers start for all connected callers (PvP can have multiple simultaneous callers)
- On round end, fixed-duration round-advance timers start for all players; when a player confirms (or the timer expires), they are marked as ready; once all players confirm, the next round begins
- When a player acts, their timer stops (bank time deducted) and other callers' meld timers are cancelled (no bank time deducted)
- On game end, all player timers are cleaned up

### AI Player Identity Separation

The game logic layer (`MahjongPlayer`, `MahjongRoundState`) has no knowledge of player types. `MahjongPlayer` has no `is_ai_player` field.

AI player identity is managed exclusively by `AIPlayerController.is_ai_player(seat)` at the service layer. Client-facing DTOs (`PlayerView`, `PlayerStanding`, `PlayerInfo`) retain `is_ai_player` for display purposes, populated from `AIPlayerController.ai_player_seats` when constructing views via `get_player_view(ai_player_seats=...)` and `finalize_game(ai_player_seats=...)`.

### Replay System

The replay adapter (`src/game/replay/`) enables deterministic replay of game sessions through `MahjongGameService`'s public API.

- **ReplayInput** defines a versioned input format: a seed, 4 player names, an ordered sequence of player actions, and an optional `wall` (pre-arranged tile order for testing)
- **ReplayTrace** captures full output: startup events, per-step state transitions (`state_before`/`state_after`), and final state
- **run_replay()** / **run_replay_async()** feed recorded actions through the service and return a trace; support `auto_confirm_rounds` (injects synthetic `CONFIRM_ROUND` steps) and `auto_pass_calls` (injects synthetic `PASS` steps for pending call prompts)
- **ReplayServiceProtocol** is the replay-facing protocol boundary; default factory uses `MahjongGameService(auto_cleanup=False)`
- **ReplayLoader** (`loader.py`) parses JSON Lines files (produced by `ReplayCollector`) back into `ReplayInput`; reconstructs original player name input order from the seed via RNG reconstruction; maps event types to game actions (discard, meld, ron, tsumo, etc.)
- **Determinism contract**: same seed + same input events = identical trace; AI player strategies must be deterministic given the same state
- **Dependency direction**: `game.replay` imports from `game.logic`; game logic modules never import from `game.replay` (enforced by AST-based integration test)
- `start_game()` accepts an optional `seed` parameter for deterministic game creation; when omitted, a random seed is generated

## Project Structure

```
ronin/
├── pyproject.toml
├── Makefile
└── src/
    └── game/
        ├── server/
        │   ├── app.py          # Starlette app factory
        │   ├── settings.py     # GameServerSettings (env-based config via pydantic-settings)
        │   ├── types.py        # REST API types
        │   └── websocket.py    # WebSocket endpoint
        ├── messaging/
        │   ├── protocol.py     # ConnectionProtocol interface
        │   ├── types.py        # Message schemas (Pydantic)
        │   ├── encoder.py      # MessagePack encoding/decoding
        │   ├── event_payload.py # Event payload shaping for wire and replay serialization
        │   └── router.py       # Message routing
        ├── session/
        │   ├── models.py        # Player, Game, SessionData dataclasses
        │   ├── room.py          # Room, RoomPlayer, RoomPlayerInfo for pre-game lobby
        │   ├── types.py         # Pydantic models (RoomInfo for lobby listing)
        │   ├── manager.py       # Session/game management
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
        │   ├── ai_player_controller.py # AI player turn and call handling
        │   ├── enums.py            # String enum definitions for game concepts
        │   ├── types.py            # Pydantic models for cross-component data
        │   ├── tiles.py            # Tile types and wall building
        │   ├── melds.py            # Meld detection (chi, pon, kan)
        │   ├── win.py              # Win detection and hand parsing
        │   ├── scoring.py          # Score calculation and distribution
        │   ├── riichi.py           # Riichi declaration logic
        │   ├── abortive.py         # Abortive draw detection
        │   ├── state.py            # Game state dataclasses
        │   ├── state_utils.py      # Pure functions for immutable state updates
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
- **Session helpers** (`tests/unit/session/helpers.py`) - `create_started_game()` orchestrates full room lifecycle (create/join/ready/start) for session tests

### Unit Tests (No Sockets)

Use `MockConnection` to test message handling:

```python
async def test_join_room():
    connection = MockConnection()
    router.handle_connect(connection)

    session_manager.create_room("room1", num_ai_players=3)
    await router.handle_message(connection, {
        "type": "join_room",
        "room_id": "room1",
        "player_name": "Alice",
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
        ws.send_bytes(msgpack.packb({"type": "join_room", "room_id": "test_room", "player_name": "Alice"}))
        response = msgpack.unpackb(ws.receive_bytes())
        assert response["type"] == "room_joined"
```

### Replay-Based Integration Tests

Deterministic game flow testing using the replay system with fixture files (`tests/integration/replays/fixtures/`) or programmatic `ReplayInput` construction. The replay trace enables precise state-transition assertions on `state_before`/`state_after` for each step.

### Architecture Boundary Tests

AST-based static analysis (`tests/integration/test_architecture_boundary.py`) parses all files under `game/logic/` and verifies none import from `game.replay`, enforcing the one-way dependency direction at the test level.
