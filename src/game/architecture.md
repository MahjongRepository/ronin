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

All messages are JSON with a `type` field.

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

All message handling logic operates through `ConnectionProtocol`, an abstract interface that decouples business logic from the WebSocket transport:

```
WebSocket (Starlette)
    │
    ▼
WebSocketConnection (implements ConnectionProtocol)
    │
    ▼
MessageRouter (pure Python, testable)
    │
    ▼
SessionManager (game/player management)
    │
    ▼
GameService (game logic interface)
```

This enables:
- Unit tests without real sockets (using `MockConnection`)
- Integration tests with Starlette's `TestClient`
- Easy swapping of transport layers if needed

### Game Logic Layer

The `logic/` module implements Riichi Mahjong rules:

- **MahjongService** - Main entry point implementing GameService interface
- **MahjongGame** - Manages game state across multiple rounds (hanchan)
- **Round** - Handles a single round with wall, draws, and discards
- **Turn** - Processes player actions (discard, chi, pon, kan, riichi, tsumo, ron)
- **Tiles** - 136-tile set with suits (man, pin, sou), honors (winds, dragons), and red fives
- **Melds** - Detection of valid chi, pon, and kan combinations
- **Win** - Hand parsing, yaku detection, and scoring (fu/han calculation)
- **Riichi** - Riichi declaration validation and tenpai detection
- **Abortive** - Detection of abortive draws (kyuushu kyuuhai, suufon renda, etc.)
- **Bot** - AI player for filling empty seats

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
        │   └── router.py       # Message routing
        ├── session/
        │   ├── models.py       # Player, Game dataclasses
        │   └── manager.py      # Session/game management
        ├── logic/
        │   ├── service.py          # GameService interface
        │   ├── mahjong_service.py  # MahjongService implementation
        │   ├── game.py             # MahjongGame state management
        │   ├── round.py            # Round management
        │   ├── turn.py             # Turn processing and player actions
        │   ├── tiles.py            # Tile types and wall building
        │   ├── melds.py            # Meld detection (chi, pon, kan)
        │   ├── win.py              # Win detection and hand parsing
        │   ├── riichi.py           # Riichi declaration logic
        │   ├── abortive.py         # Abortive draw detection
        │   ├── state.py            # Game state dataclasses
        │   ├── bot.py              # Bot player AI
        │   └── mock.py             # Mock implementation for testing
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

Use Starlette's `TestClient` for full WebSocket flow:

```python
def test_websocket():
    client = TestClient(app)
    client.post("/games", json={"game_id": "test_game"})
    with client.websocket_connect("/ws/test_game") as ws:
        ws.send_json({"type": "join_game", "game_id": "test_game", "player_name": "Alice"})
        response = ws.receive_json()
        assert response["type"] == "game_joined"
```
