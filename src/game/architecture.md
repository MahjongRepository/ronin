# Game Server Architecture

Game server handling real-time Mahjong gameplay via WebSocket.

**Port**: 8001

## REST API

- `GET /health` - Health check
- `GET /status` - Server status (active games, capacity)
- `GET /games` - List all active games
- `POST /games` - Create a game (called by lobby). Accepts optional `num_bots` field (0-3, defaults to 3)
## WebSocket API

### Connection

Connect to `ws://localhost:8001/ws/{game_id}` (game must be created first via lobby or `POST /games`).

### Message Format

All messages use MessagePack binary format with a `type` field. The server only accepts and sends binary WebSocket frames.

#### Client -> Server

**Join Game**
```json
{"type": "join_game", "game_id": "game123", "player_name": "Alice", "session_token": "client-generated-uuid"}
```

**Leave Game**
```json
{"type": "leave_game"}
```

**Game Action**
```json
{"type": "game_action", "action": "discard", "data": {"tile": "1m"}}
```

**Chat**
```json
{"type": "chat", "text": "Hello!"}
```

**Ping** (heartbeat keep-alive)
```json
{"type": "ping"}
```

#### Server -> Client

**Game Joined**
```json
{"type": "game_joined", "game_id": "game123", "players": ["Alice", "Bob"], "session_token": "uuid-token"}
```

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
{"type": "game_started", "players": [{"seat": 0, "name": "Alice", "is_bot": false}, ...]}
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
- `game_not_found` - The requested game does not exist
- `game_started` - Game has already started and cannot accept new players
- `game_full` - Game has reached its human player capacity (4 - num_bots)
- `already_in_game` - Player tried to join a game while already in one
- `name_taken` - Player name is already used in the game
- `not_in_game` - Player tried to perform an action without being in a game

## Internal Architecture

Clean architecture pattern with clear separation between layers:

- **Transport Layer** (`server/`) - Starlette WebSocket + REST handling
- **Application Layer** (`messaging/`, `session/`) - Message routing and session management
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
    │
    ▼
GameService (game logic interface) → returns list[ServiceEvent]
    Methods: start_game, handle_action, get_player_seat, handle_timeout,
             replace_player_with_bot, process_bot_actions_after_replacement
```

This enables:
- Unit tests without real sockets (using `MockConnection`)
- Integration tests with Starlette's `TestClient`
- Easy swapping of transport layers if needed

### Event System

The game service communicates through a typed event pipeline:

- **GameEvent** (Pydantic base, `game.logic.events`) - Domain events like DrawEvent (carries tile_id and available_actions), DiscardEvent, MeldEvent, DoraRevealedEvent, RoundEndEvent, FuritenEvent, GameStartedEvent, RoundStartedEvent, etc. All events use integer tile IDs only (no string representations). Game start produces a two-phase sequence: `GameStartedEvent` (broadcast) followed by `RoundStartedEvent` (per-seat events with full GameView).
- **ServiceEvent** - Transport container wrapping a GameEvent with typed routing metadata (`BroadcastTarget` or `SeatTarget`). Events are serialized as flat top-level messages on the wire (no wrapper envelope). The `ReplayCollector` persists broadcast gameplay events and seat-targeted `DrawEvent` events (null `tile_id` draws excluded, `available_actions` stripped); per-seat `RoundStartedEvent` views are merged into a single record with all players' tiles for full game reconstruction.
- **EventType** - String enum defining all event type identifiers
- `convert_events()` transforms GameEvent lists into ServiceEvent lists; DISCARD prompts are split per-seat via `_split_discard_prompt_for_seat()` into RON or MELD wire events (ron-dominant: if a seat has both ron and meld eligibility, only a RON prompt is sent)
- `extract_round_result()` extracts round results from ServiceEvent lists

### Game Logic Layer

The `logic/` module implements Riichi Mahjong rules:

- **MahjongService** - Unified orchestration entry point implementing GameService interface; dispatches both human and bot actions through the same handler pipeline; manages bot followup loop (`_process_bot_followup`) and bot call response dispatch (`_dispatch_bot_call_responses`); tracks per-player furiten state and emits `FuritenEvent` on state transitions; delegates round-advance confirmation tracking to `RoundAdvanceManager`; returns `list[ServiceEvent]`
- **RoundAdvanceManager** - Manages round advancement confirmation state (`PendingRoundAdvance`) for all games; tracks which human seats still need to confirm readiness between rounds; bot seats are pre-confirmed at setup; provides `setup_pending()`, `confirm_seat()`, `is_pending()`, `get_unconfirmed_seats()`, `is_seat_required()`, and `cleanup_game()`
- **MahjongGame** - Manages game state across multiple rounds (hanchan); uma/oka end-game score adjustment
- **Round** - Handles a single round with wall, draws, discards, dead wall replenishment, pending dora reveal, nagashi mangan detection, and keishiki tenpai with pure karaten exclusion
- **Turn** - Processes player actions and returns typed GameEvent objects
- **Actions** - Builds available actions as `AvailableActionItem` models (discardable tiles, riichi, tsumo, kan)
- **ActionHandlers** - Validates and processes player actions using typed Pydantic data models (DiscardActionData, RiichiActionData, etc.); call responses (pon, chi, ron, open kan) record intent on `PendingCallPrompt`; `_validate_caller_action_matches_prompt()` enforces per-caller action validity (ron callers can only CALL_RON on DISCARD prompts, meld callers validated against their available call types); `handle_pass` removes the caller from `pending_seats` and applies furiten (for DISCARD prompts, only ron callers receive furiten) without emitting any events; resolution triggers when all callers have responded or passed via `resolve_call_prompt()` from `call_resolution`
- **CallResolution** (`call_resolution.py`) - Resolves pending call prompts after all callers respond; picks winning response by priority (ron > pon/kan > chi > all pass); handles triple ron abortive draw, double/single ron, meld resolution, and chankan decline completion; for DISCARD prompts, `_finalize_discard_post_ron_check()` performs deferred dora reveal and riichi finalization after no ron, and `_resolve_all_passed_discard()` handles the all-passed case (dora/riichi already finalized, just advances turn)
- **Matchmaker** - Assigns human players to randomized seats and fills remaining seats with bots; supports 1-4 humans based on `num_bots` setting; returns `list[SeatConfig]`
- **TurnTimer** - Server-side per-player bank time management with async timeout callbacks for turns, meld decisions, and round-advance confirmations; each human player gets an independent timer instance
- **BotController** - Pure decision-maker for bot players using `dict[int, BotPlayer]` seat-to-bot mapping; provides `is_bot()`, `add_bot()`, `get_turn_action()`, and `get_call_response()` without any orchestration or game state mutation; for DISCARD prompts, dispatches to ron or meld logic based on caller type (`int` = ron, `MeldCaller` = meld); supports runtime bot addition for disconnect-to-bot replacement
- **Enums** - String enum definitions: `GameAction` (includes `CONFIRM_ROUND`), `PlayerAction`, `MeldCallType`, `KanType`, `CallType` (RON, MELD, CHANKAN, DISCARD), `AbortiveDrawType`, `RoundResultType`, `WindName`, `MeldViewType`, `BotType`, `TimeoutType` (`TURN`, `MELD`, `ROUND_ADVANCE`); `MELD_CALL_PRIORITY` dict maps `MeldCallType` to resolution priority (kan > pon > chi)
- **Types** - Pydantic models for cross-component data: `SeatConfig`, `GamePlayerInfo` (player identity for game start broadcast), round results (`TsumoResult`, `RonResult`, `DoubleRonResult`, `ExhaustiveDrawResult`, `AbortiveDrawResult`, `NagashiManganResult`), action data models, player views (`GameView`, `PlayerView`), `MeldCaller` (seat and call_type only, no server-internal fields), `BotAction`, `AvailableActionItem`; `RoundResult` union type
- **Tiles** - 136-tile set with suits (man, pin, sou), honors (winds, dragons), and red fives
- **Melds** - Detection of valid chi, pon, and kan combinations; kuikae restriction calculation; pao liability detection
- **Win** - Win detection, furiten checking (permanent, temporary, riichi furiten), renhou detection, chankan validation, and hand parsing
- **Scoring** - Score calculation (fu/han, point distribution for tsumo/ron); pao liability scoring (tsumo: liable pays full, ron: 50/50 split); nagashi mangan scoring; double yakuman scoring; returns typed result models
- **Riichi** - Riichi declaration validation and tenpai detection
- **Abortive** - Detection of abortive draws (kyuushu kyuuhai, suufon renda, etc.); returns `AbortiveDrawResult`
- **Bot** - AI player for filling empty seats; returns `BotAction` model
- **Settings** (`settings.py`) - `GameSettings` Pydantic model with all configurable game rules; `validate_settings()` startup guard rejecting unsupported combinations; `GameType`/`EnchousenType`/`RenhouValue`/`LeftoverRiichiBets` enums; `build_optional_rules()` for scoring library integration; `get_wind_thresholds()` for wind-round boundary computation
- **State** - Frozen Pydantic game state models: `MahjongPlayer`, `MahjongRoundState`, `MahjongGameState`, `PendingCallPrompt`, `CallResponse`; all state is immutable (`frozen=True`); state updates use `model_copy(update={...})` pattern; settings live only on `MahjongGameState`, not on `MahjongRoundState`; `MahjongPlayer.score` is required (no default)
- **MeldWrapper** (`meld_wrapper.py`) - `FrozenMeld` immutable wrapper for external `mahjong.meld.Meld` class; provides true immutability by storing meld data in frozen Pydantic model; converts to/from `Meld` at boundaries for library compatibility; `frozen_melds_to_melds()` utility for batch conversion
- **StateUtils** (`state_utils.py`) - Helper functions for immutable state updates: `update_player()`, `add_tile_to_player()`, `remove_tile_from_player()`, `add_discard()`, `add_meld()`, `reveal_dora()`, `advance_turn()`, etc.
- **Exceptions** (`exceptions.py`) - Typed domain exception hierarchy rooted in `GameRuleError`; subclasses: `InvalidDiscardError`, `InvalidMeldError`, `InvalidRiichiError`, `InvalidWinError`, `InvalidActionError`, `UnsupportedSettingsError`. Domain modules raise these instead of raw `ValueError`. Action handlers catch `GameRuleError` and convert to `ErrorEvent`. Separately, `InvalidGameActionError` (not a `GameRuleError` subclass) is raised for provably invalid actions (fabricated data, modified client); caught by `SessionManager` to disconnect the offender (WebSocket close code 1008) and replace with a bot. The broad `except Exception` containment in `MessageRouter` is preserved as a fatal safety net.

### Pending Call Prompt System

The game uses a unified call-response system where all players (human and bot) respond to call opportunities through the same code path.

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

This eliminates the previous duplication where bot and human call responses had separate orchestration paths.

### Unified Turn Loop

`MahjongGameService` orchestrates all turns through a single dispatch pipeline:

1. Human actions enter via `handle_action()` -> `_dispatch_and_process()` -> action handlers
2. After each human action, `_process_bot_followup()` iterates bot turns through the same `_dispatch_and_process()` path
3. Bot call responses are dispatched through `_dispatch_bot_call_responses()` -> `_dispatch_action()` -> same action handlers

`BotController` is a pure decision-maker: `get_turn_action()` returns action data for a bot's turn, `get_call_response()` returns the bot's response to a call prompt. Neither method modifies game state or calls handlers directly. All state mutation flows through `MahjongGameService`.

### Unified Game Creation

Games use a `num_bots` parameter (0-3) instead of separate game modes. The `num_bots` value determines how many human players are needed: `num_humans_needed = 4 - num_bots`.

- `num_bots=3` (default): game starts when 1 human joins, 3 seats filled with bots
- `num_bots=0`: game waits for 4 humans, no bots
- `num_bots=1` or `num_bots=2`: game waits for the required humans, remaining seats filled with bots

The `num_bots` is set at game creation time via `POST /games` and stored on the `Game` dataclass. `SessionManager.join_game()` starts the game when `player_count == num_humans_needed`.

### Disconnect-to-Bot Replacement

When a human player disconnects from a started game (either by closing the connection or by sending a provably invalid game action):
1. The player's connection is closed (code 1008 for invalid actions, normal close for voluntary disconnect)
2. The player is removed from the session layer (`game.players`)
3. If other humans remain, `replace_player_with_bot()` registers a bot at the disconnected player's seat
4. The disconnected player's timer is cancelled
5. `process_bot_actions_after_replacement()` handles any pending turn, call prompt, or round-advance confirmation for the replaced seat
6. If the last human disconnects, the game is cleaned up (no all-bot games)

For invalid game actions, the `InvalidGameActionError` exception carries a `seat` attribute for blame attribution: when a resolution-time error is caused by a different player's prior bad data, the offending seat (not the action requester) is disconnected.

### Session Identity

Players provide a `session_token` (UUID) when joining a game. The client generates the token (via `crypto.randomUUID()` in web, `uuid.uuid4()` in bot) and includes it as a required field in the `join_game` message. The server stores the token in `SessionStore` (`session/session_store.py`) and echoes it back in the `game_joined` response. The client persists the token in `sessionStorage` (scoped by game ID) and reuses it on reconnection.

Session lifecycle:
- **Created**: When a player joins a game (`join_game`)
- **Seat bound**: When the game starts, the player's seat is recorded on the session
- **Marked disconnected**: When a player disconnects from a started game (timestamp recorded)
- **Removed**: When a player leaves before the game starts, or on defensive cleanup
- **Cleaned up**: When a game ends and is empty, all sessions for that game are removed

Session data (`SessionData`) stores: session token, player name, game ID, seat number, and disconnect timestamp. Sessions are in-memory only (no persistence). Reconnection logic (rebinding a new WebSocket to an existing session) is not yet implemented.

### Per-Player Timers

Each human player gets an independent `TurnTimer` instance, managed by `TimerManager` (`session/timer_manager.py`). `SessionManager` delegates all timer operations to `TimerManager` and provides a timeout callback.

Timer behavior:
- On round start, round bonus is added to all player timers
- On turn start, the current seat's timer starts counting bank time
- On call prompt, meld timers start for all connected human callers (PvP can have multiple simultaneous callers)
- On round end, fixed-duration round-advance timers start for all human players; when a player confirms (or the timer expires), they are marked as ready; once all humans confirm, the next round begins
- When a player acts, their timer stops (bank time deducted) and other callers' meld timers are cancelled (no bank time deducted)
- On game end, all player timers are cleaned up

### Bot Identity Separation

The game logic layer (`MahjongPlayer`, `MahjongRoundState`) has no knowledge of player types. `MahjongPlayer` has no `is_bot` field.

Bot identity is managed exclusively by `BotController.is_bot(seat)` at the service layer. Client-facing DTOs (`PlayerView`, `PlayerStanding`, `PlayerInfo`) retain `is_bot` for display purposes, populated from `BotController.bot_seats` when constructing views via `get_player_view(bot_seats=...)` and `finalize_game(bot_seats=...)`.

### Replay System

The replay adapter (`src/game/replay/`) enables deterministic replay of game sessions through `MahjongGameService`'s public API.

- **ReplayInput** defines a versioned input format: a seed, 4 player names, and an ordered sequence of human actions
- **ReplayTrace** captures full output: startup events, per-step state transitions (`state_before`/`state_after`), and final state
- **run_replay()** / **run_replay_async()** feed recorded actions through the service and return a trace
- **ReplayServiceProtocol** is the replay-facing protocol boundary; default factory uses `MahjongGameService(auto_cleanup=False)`
- **Determinism contract**: same seed + same input events = identical trace; bot strategies must be deterministic given the same state
- **Dependency direction**: `game.replay` imports from `game.logic`; game logic modules never import from `game.replay`
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
        │   ├── types.py        # REST API types
        │   └── websocket.py    # WebSocket endpoint
        ├── messaging/
        │   ├── protocol.py     # ConnectionProtocol interface
        │   ├── mock.py         # MockConnection for testing
        │   ├── types.py        # Message schemas (Pydantic)
        │   ├── encoder.py      # MessagePack encoding/decoding
        │   └── router.py       # Message routing
        ├── session/
        │   ├── models.py        # Player, Game, SessionData dataclasses
        │   ├── types.py         # Pydantic models (GameInfo)
        │   ├── manager.py       # Session/game management
        │   ├── session_store.py # In-memory session identity persistence
        │   ├── replay_collector.py # Collects broadcast events and merges per-seat round_started views for post-game persistence
        │   ├── timer_manager.py # Per-player turn timer lifecycle
        │   └── heartbeat.py     # Client liveness heartbeat monitor
        ├── replay/
        │   ├── __init__.py      # Public API re-exports
        │   ├── models.py        # ReplayInput, ReplayTrace, ReplayStep, error types
        │   └── runner.py        # ReplayServiceProtocol, run_replay/run_replay_async
        ├── logic/
        │   ├── service.py          # GameService interface
        │   ├── mahjong_service.py  # MahjongService orchestration
        │   ├── game.py             # MahjongGame state management
        │   ├── round.py            # Round management
        │   ├── turn.py             # Turn processing, returns typed events
        │   ├── actions.py          # Available actions builder
        │   ├── action_handlers.py  # Action validation and processing
        │   ├── action_result.py    # Shared ActionResult type and helpers
        │   ├── call_resolution.py  # Call resolution subsystem (ron/meld/pass)
        │   ├── events.py           # Domain event models, ServiceEvent, convert_events()
        │   ├── exceptions.py       # Typed domain exceptions (GameRuleError hierarchy)
        │   ├── round_advance.py    # Round advancement confirmation state machine
        │   ├── bot_controller.py   # Bot turn and call handling
        │   ├── enums.py            # String enum definitions for game concepts
        │   ├── types.py            # Pydantic models for cross-component data
        │   ├── tiles.py            # Tile types and wall building
        │   ├── melds.py            # Meld detection (chi, pon, kan)
        │   ├── win.py              # Win detection and hand parsing
        │   ├── scoring.py          # Score calculation and distribution
        │   ├── riichi.py           # Riichi declaration logic
        │   ├── abortive.py         # Abortive draw detection
        │   ├── state.py            # Game state dataclasses
        │   ├── bot.py              # Bot player AI
        │   ├── matchmaker.py       # Seat assignment and bot filling
        │   ├── timer.py            # Turn timer with bank time management
        │   └── mock.py             # MockGameService for testing
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-all-checks       # Run all checks
```

## Testing Strategy

### Unit Tests (No Sockets)

Use `MockConnection` to test message handling:

```python
async def test_join_game():
    connection = MockConnection()
    router.handle_connect(connection)

    await router.handle_message(connection, {
        "type": "join_game",
        "game_id": "game1",
        "player_name": "Alice",
    })

    response = connection.sent_messages[0]
    assert response["type"] == "game_joined"
    assert "session_token" in response
```

### Integration Tests (With TestClient)

Use Starlette's `TestClient` for full WebSocket flow with MessagePack:

```python
import msgpack

def test_websocket():
    client = TestClient(app)
    client.post("/games", json={"game_id": "test_game"})
    with client.websocket_connect("/ws/test_game") as ws:
        ws.send_bytes(msgpack.packb({"type": "join_game", "game_id": "test_game", "player_name": "Alice"}))
        response = msgpack.unpackb(ws.receive_bytes())
        assert response["type"] == "game_joined"
        assert "session_token" in response
```
