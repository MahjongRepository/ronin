# Game Server Architecture

Game server handling real-time Mahjong gameplay via WebSocket.

**Port**: 8001

## REST API

- `GET /health` - Health check
- `GET /status` - Server status (active rooms, capacity)
- `POST /rooms` - Create a room (called by lobby)

## WebSocket API

### Connection

Connect to `ws://localhost:8001/ws/{room_id}` (room must be created first via lobby or `POST /rooms`).

### Message Format

All messages are JSON with a `type` field.

#### Client -> Server

**Join Room**
```json
{"type": "join_room", "room_id": "room123", "player_name": "Alice"}
```

**Leave Room**
```json
{"type": "leave_room"}
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

**Room Joined**
```json
{"type": "room_joined", "room_id": "room123", "players": ["Alice", "Bob"]}
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
{"type": "error", "code": "room_full", "message": "Room is full"}
```

Error codes:
- `room_full` - Room has reached maximum player capacity (4)
- `already_in_room` - Player tried to join a room while already in one
- `name_taken` - Player name is already used in the room
- `not_in_room` - Player tried to perform an action without being in a room

## Internal Architecture

Clean architecture pattern with clear separation between layers:

- **Transport Layer** (`server/`) - Starlette WebSocket + REST handling
- **Application Layer** (`messaging/`, `session/`) - Message routing and session management
- **Domain Layer** (`logic/`) - Game logic (currently mocked)

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
SessionManager (room/player management)
    │
    ▼
GameService (game logic interface)
```

This enables:
- Unit tests without real sockets (using `MockConnection`)
- Integration tests with Starlette's `TestClient`
- Easy swapping of transport layers if needed

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
        │   ├── models.py       # Player, Room dataclasses
        │   └── manager.py      # Session/room management
        ├── logic/
        │   ├── service.py      # GameService interface
        │   └── mock.py         # Mock implementation
        └── tests/
            ├── unit/
            └── integration/
```

## Running

```bash
make run-game   # Start server on port 8001
make test-game  # Run game tests
make lint       # Run linter
make format     # Format code
```

## Testing Strategy

### Unit Tests (No Sockets)

Use `MockConnection` to test message handling:

```python
async def test_join_room():
    connection = MockConnection()
    router.handle_connect(connection)

    await router.handle_message(connection, {
        "type": "join_room",
        "room_id": "room1",
        "player_name": "Alice",
    })

    assert connection.sent_messages[0]["type"] == "room_joined"
```

### Integration Tests (With TestClient)

Use Starlette's `TestClient` for full WebSocket flow:

```python
def test_websocket():
    client = TestClient(app)
    client.post("/rooms", json={"room_id": "test_room"})
    with client.websocket_connect("/ws/test_room") as ws:
        ws.send_json({"type": "join_room", "room_id": "test_room", "player_name": "Alice"})
        response = ws.receive_json()
        assert response["type"] == "room_joined"
```
