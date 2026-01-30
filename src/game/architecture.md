# Game Server Architecture

Game server handling real-time Mahjong gameplay via WebSocket.

**Port**: 8001

## REST API

- `GET /health` - Health check
- `GET /status` - Server status (active games, capacity)
- `GET /games` - List all active games
- `POST /games` - Create a game (called by lobby)
- `GET /static/*` - Static file serving

## WebSocket API

### Connection

Connect to `ws://localhost:8001/ws/{game_id}` (game must be created first via lobby or `POST /games`).

### Message Format

All messages use MessagePack binary format with a `type` field. The server only accepts and sends binary WebSocket frames.

#### Client -> Server

**Join Game**
```json
{"type": "join_game", "game_id": "game123", "player_name": "Alice"}
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

#### Server -> Client

**Game Joined**
```json
{"type": "game_joined", "game_id": "game123", "players": ["Alice", "Bob"]}
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

**Game Event**
```json
{"type": "game_event", "event": "tile_discarded", "data": {...}}
```

**Chat**
```json
{"type": "chat", "player_name": "Alice", "text": "Hello!"}
```

**Error**
```json
{"type": "error", "code": "game_full", "message": "Game is full"}
```

Error codes:
- `game_full` - Game has reached maximum player capacity (4)
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
SessionManager (game/player management, timer lifecycle, concurrency locks)
    │
    ▼
GameService (game logic interface) → returns list[ServiceEvent]
    Methods: start_game, handle_action, get_player_seat, handle_timeout
```

This enables:
- Unit tests without real sockets (using `MockConnection`)
- Integration tests with Starlette's `TestClient`
- Easy swapping of transport layers if needed

### Event System

The game service communicates through a typed event pipeline:

- **GameEvent** (Pydantic base) - Domain events like DrawEvent, DiscardEvent, MeldEvent, TurnEvent, RoundEndEvent, etc.
- **ServiceEvent** - Transport container wrapping a GameEvent with routing metadata (event type string, target)
- **EventType** - String enum defining all event type identifiers
- `convert_events()` transforms GameEvent lists into ServiceEvent lists
- `extract_round_result()` extracts round results from ServiceEvent lists

### Game Logic Layer

The `logic/` module implements Riichi Mahjong rules:

- **MahjongService** - Unified orchestration entry point implementing GameService interface; dispatches both human and bot actions through the same handler pipeline; manages bot followup loop (`_process_bot_followup`) and bot call response dispatch (`_dispatch_bot_call_responses`); returns `list[ServiceEvent]`
- **MahjongGame** - Manages game state across multiple rounds (hanchan); uma/oka end-game score adjustment
- **Round** - Handles a single round with wall, draws, discards, dead wall replenishment, pending dora reveal, nagashi mangan detection, and keishiki tenpai with pure karaten exclusion
- **Turn** - Processes player actions and returns typed GameEvent objects
- **Actions** - Builds available actions as `AvailableActionItem` models (discardable tiles, riichi, tsumo, kan)
- **ActionHandlers** - Validates and processes player actions using typed Pydantic data models (DiscardActionData, RiichiActionData, etc.); call responses (pon, chi, ron, open kan) record intent on `PendingCallPrompt`; `handle_pass` removes the caller from `pending_seats` and applies furiten without recording a response; resolution triggers when all callers have responded or passed via `resolve_call_prompt()`
- **Matchmaker** - Assigns human players to random seats and fills remaining with bots; returns `list[SeatConfig]`
- **TurnTimer** - Server-side bank time management with async timeout callbacks for turns and meld decisions
- **BotController** - Pure decision-maker for bot players using `dict[int, BotPlayer]` seat-to-bot mapping; provides `is_bot()`, `get_turn_action()`, and `get_call_response()` without any orchestration or game state mutation
- **Enums** - String enum definitions: `GameAction`, `PlayerAction`, `MeldCallType`, `KanType`, `CallType`, `AbortiveDrawType`, `RoundResultType`, `WindName`, `MeldViewType`, `BotType`, `TimeoutType`
- **Types** - Pydantic models for cross-component data: `SeatConfig`, round results (`TsumoResult`, `RonResult`, `DoubleRonResult`, `ExhaustiveDrawResult`, `AbortiveDrawResult`, `NagashiManganResult`), action data models, player views (`GameView`, `PlayerView`), `MeldCaller`, `BotAction`, `AvailableActionItem`; `RoundResult` union type
- **Tiles** - 136-tile set with suits (man, pin, sou), honors (winds, dragons), and red fives
- **Melds** - Detection of valid chi, pon, and kan combinations; kuikae restriction calculation; pao liability detection
- **Win** - Win detection, furiten checking (permanent, temporary, riichi furiten), renhou detection, chankan validation, and hand parsing
- **Scoring** - Score calculation (fu/han, point distribution for tsumo/ron); pao liability scoring (tsumo: liable pays full, ron: 50/50 split); nagashi mangan scoring; double yakuman scoring; returns typed result models
- **Riichi** - Riichi declaration validation and tenpai detection
- **Abortive** - Detection of abortive draws (kyuushu kyuuhai, suufon renda, etc.); returns `AbortiveDrawResult`
- **Bot** - AI player for filling empty seats; returns `BotAction` model
- **State** - Game state dataclasses including `MahjongPlayer`, `MahjongRoundState`, `MahjongGameState`, `PendingCallPrompt`, and `CallResponse`

### Pending Call Prompt System

The game uses a unified call-response system where all players (human and bot) respond to call opportunities through the same code path.

When a discard or chankan creates call opportunities, `process_discard_phase()` or `_process_added_kan_call()` sets a `PendingCallPrompt` on `MahjongRoundState` with:
- `call_type` - the type of call opportunity (ron, meld, chankan)
- `tile_id` - the tile being called on
- `from_seat` - the seat that discarded or played the tile
- `pending_seats` - set of seats that have not yet responded
- `callers` - the original eligible callers list
- `responses` - collected `CallResponse` objects

Each caller responds through the standard action handlers (`handle_pass`, `handle_pon`, `handle_chi`, `handle_ron`, `handle_kan`). These handlers record the response and remove the caller from `pending_seats`. When `pending_seats` is empty, `resolve_call_prompt()` picks the winner by priority (ron > pon/kan > chi > all pass) and executes the action.

This eliminates the previous duplication where bot and human call responses had separate orchestration paths.

### Unified Turn Loop

`MahjongGameService` orchestrates all turns through a single dispatch pipeline:

1. Human actions enter via `handle_action()` -> `_dispatch_and_process()` -> action handlers
2. After each human action, `_process_bot_followup()` iterates bot turns through the same `_dispatch_and_process()` path
3. Bot call responses are dispatched through `_dispatch_bot_call_responses()` -> `_call_handler()` -> same action handlers

`BotController` is a pure decision-maker: `get_turn_action()` returns action data for a bot's turn, `get_call_response()` returns the bot's response to a call prompt. Neither method modifies game state or calls handlers directly. All state mutation flows through `MahjongGameService`.

### Bot Identity Separation

The game logic layer (`MahjongPlayer`, `MahjongRoundState`) has no knowledge of player types. `MahjongPlayer` has no `is_bot` field.

Bot identity is managed exclusively by `BotController.is_bot(seat)` at the service layer. Client-facing DTOs (`PlayerView`, `PlayerStanding`, `PlayerInfo`) retain `is_bot` for display purposes, populated from `BotController.bot_seats` when constructing views via `get_player_view(bot_seats=...)` and `finalize_game(bot_seats=...)`.

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
        │   ├── events.py       # Typed events, ServiceEvent, EventType enum
        │   ├── encoder.py      # MessagePack encoding/decoding
        │   └── router.py       # Message routing
        ├── session/
        │   ├── models.py       # Player, Game dataclasses
        │   ├── types.py        # Pydantic models (GameInfo)
        │   └── manager.py      # Session/game management
        ├── logic/
        │   ├── service.py          # GameService interface
        │   ├── mahjong_service.py  # MahjongService orchestration
        │   ├── game.py             # MahjongGame state management
        │   ├── round.py            # Round management
        │   ├── turn.py             # Turn processing, returns typed events
        │   ├── actions.py          # Available actions builder
        │   ├── action_handlers.py  # Action validation and processing
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
        ├── static/
        │   └── game.html       # Game WebSocket UI
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-all    # Run both lobby and game servers
make run-game   # Start server on port 8001
make test-game  # Run game tests
make lint       # Run linter
make format     # Format code
make typecheck  # Run type checking (ty)
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

    assert connection.sent_messages[0]["type"] == "game_joined"
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
```
