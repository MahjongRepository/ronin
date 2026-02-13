# Ronin - Architecture Overview

## Services

The system consists of two backend services and a TypeScript client in a unified project:

- **Lobby Service** (`src/lobby/`) - Portal for game discovery and creation (port 8000)
- **Game Service** (`src/game/`) - Real-time Riichi Mahjong gameplay server with full game logic (port 8001)
- **Client** (`client/`) - TypeScript + SASS frontend using Bun dev server (port 3000)

## Room & Game Creation Flow

Players create rooms (pre-game lobbies) where they gather, chat, and ready up before the game starts. The room creator specifies `num_bots` (0-3), which determines how many human players are needed (4 - num_bots).

- `num_bots=3` (default): game starts when 1 human readies up (1 human + 3 bots)
- `num_bots=0`: game waits for 4 humans to ready up (pure PvP)
- `num_bots=1` or `num_bots=2`: game waits for the required number of humans to ready up, then fills remaining seats with bots

### API flow

1. Client calls `POST /rooms` on lobby with `{"num_bots": N}` (defaults to 3)
2. Lobby selects a healthy game server
3. Lobby generates room ID and calls `POST /rooms` on game server with `num_bots`
4. Game server creates an empty room with specified bot count
5. Lobby returns WebSocket URL to client
6. Client connects to `ws://game-server/ws/{room_id}`
7. Client sends `join_room` message with player name
8. Players chat and toggle ready status in the room lobby
9. When all required humans are ready, the server transitions the room to a game on the same WebSocket connection

Each human player in the game has independent bank time managed by per-player timers.

### Disconnect-to-bot replacement

When a human player disconnects from a started game, they are replaced with a bot instead of ending the game. The bot takes over the disconnected player's seat and continues playing. An application-level heartbeat (ping/pong) monitors client liveness; if no ping is received within 30 seconds, the server disconnects the client and triggers bot replacement. When the last human disconnects, the game is cleaned up (no all-bot games run without observers).

### Round Advancement

After a round ends, the server enters a waiting state. Human players must send a `confirm_round` action (or a 15-second timeout fires) before the next round begins. Bot seats are auto-confirmed. This allows clients to display round results before advancing.

### Web UI flow (client SPA on port 3000)

1. User opens `http://localhost:3000` which loads the SPA
2. Hash-based router renders lobby view at `#/`
3. Lobby view fetches rooms via `GET /rooms` (CORS-enabled on lobby server)
4. User clicks "Create Room" or "Join" on an existing room
5. Client stores WebSocket URL and player name in sessionStorage
6. Router navigates to `#/room/<id>` and renders room view
7. Room view connects via WebSocket using MessagePack binary frames
8. Client sends `join_room` message and enters the pre-game lobby (player list, chat, ready toggle)
9. When all required humans are ready, the server sends `game_starting`
10. Client hands off the WebSocket to the game view (no reconnection needed) and navigates to `#/game/<id>`

## Web UI

- **Client** (`client/`, port 3000) - Primary frontend. TypeScript + SASS single-page application served by Bun's dev server. Uses lit-html for templating, hash-based routing (`#/` for lobby, `#/room/:id` for room, `#/game/:id` for game), and MessagePack for WebSocket communication. Entry point is `client/index.html`.

## Project Structure

```
ronin/
├── pyproject.toml              # Unified project config
├── Makefile                    # Build targets for all services
├── client/                     # TypeScript + SASS frontend (Bun)
│   ├── index.html              # HTML entry point
│   ├── package.json            # Bun project config
│   ├── tsconfig.json           # TypeScript configuration
│   └── src/
│       ├── index.ts            # App entry point, initializes router
│       ├── router.ts           # Hash-based SPA router
│       ├── api.ts              # Lobby API client (fetch wrappers)
│       ├── websocket.ts        # WebSocket manager with MessagePack
│       ├── socket-handoff.ts   # WebSocket handoff (room→game)
│       ├── views/
│       │   ├── lobby.ts        # Lobby view (list/create rooms)
│       │   ├── room.ts         # Room view (pre-game lobby)
│       │   └── game.ts         # Game view (WebSocket log panel)
│       └── styles/
│           ├── main.scss       # SASS entry point (imports partials)
│           ├── _variables.scss # Shared design tokens
│           ├── _reset.scss     # CSS reset
│           ├── _layout.scss    # Shared layout and button styles
│           ├── _lobby.scss     # Lobby view styles
│           ├── _room.scss      # Room view styles
│           └── _game.scss      # Game view styles
├── src/
│   ├── config/
│   │   └── servers.yaml        # Game server registry
│   ├── lobby/                  # Portal service (REST API)
│   │   ├── server/
│   │   ├── registry/
│   │   ├── games/
│   │   ├── static/             # Lobby HTML pages
│   │   └── tests/
│   ├── game/                   # Game server (WebSocket + REST)
│   │   ├── server/
│   │   ├── messaging/
│   │   ├── session/
│   │   ├── logic/              # Riichi Mahjong rules implementation
│   │   └── tests/
│   └── shared/                 # Shared utilities (logging, validators, storage)
```

## Running Locally

Requires [uv](https://docs.astral.sh/uv/) for Python package management and [Bun](https://bun.sh/) for the TypeScript client. Dependencies are installed automatically when running commands.

```bash
# Run all servers together (recommended for local testing)
make run-local-server
```

Using the Web UI:
1. Run `make run-local-server` to start all servers
2. Open http://localhost:3000 in your browser
3. Create or join a room from the lobby view
4. Ready up in the room lobby; game starts when all required humans are ready
5. Game view receives the WebSocket handoff and displays server messages in a log panel

Using the API directly:
```bash
# List available rooms
curl http://localhost:8000/rooms

# Create a room with 3 bots (default, needs 1 human to start)
curl -X POST http://localhost:8000/rooms

# Create a room with custom bot count (waits for required humans)
curl -X POST http://localhost:8000/rooms -H 'Content-Type: application/json' -d '{"num_bots": 1}'

# Response:
# {"room_id": "abc123", "websocket_url": "ws://localhost:8001/ws/abc123", "server_name": "local-1"}
```

## Development

```bash
make run-all-checks       # Run all checks (format, lint, typecheck, test, client typecheck)
```

## Replay Data Security & Retention

Replay files contain concealed game data (player hands, draw tiles, dora indicators, winner hand details) and are treated as sensitive artifacts.

**Filesystem permissions:**
- Replay directory: owner-only (`0o700`)
- Replay files: owner-only read/write (`0o600`)
- Files are written atomically via `os.open` with explicit mode to avoid TOCTOU permission windows

**Retention:**
- `LocalReplayStorage.cleanup_old_replays(max_age_seconds)` removes replay files whose modification time is older than the specified threshold
- Cleanup is designed to be called by an external scheduler (cron job, periodic task) rather than running automatically
- Errors on individual files are logged and skipped so one bad file does not block the rest

**Access:**
- Only the process owner (game server) can read or write replay files
- No read/parse/load functionality exists; replay files are write-only artifacts for post-game analysis
- Concealed replay data (draw tiles, per-seat hands, winner hand details) is captured from canonical `SeatTarget` events (`DrawEvent`, `RoundStartedEvent`) and broadcast `RoundEndEvent` by the `ReplayCollector`; these events are never delivered to unintended client connections

## Next Steps

1. Add reconnection support (rebind new WebSocket to existing session, grace period before bot replacement)
2. Add game state synchronization
3. Add authentication
4. Add persistence (game history, player stats)
