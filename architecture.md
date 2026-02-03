# Ronin - Architecture Overview

## Services

The system consists of two backend services and a TypeScript client in a unified project:

- **Lobby Service** (`src/lobby/`) - Portal for game discovery and creation (port 8000)
- **Game Service** (`src/game/`) - Real-time Riichi Mahjong gameplay server with full game logic (port 8001)
- **Client** (`client/`) - TypeScript + SASS frontend using Bun dev server (port 3000)

## Game Creation Flow

Unified game creation: the creator specifies `num_bots` (0-3), which determines how many human players are needed (4 - num_bots). Players browse and join existing games from the lobby.

- `num_bots=3` (default): game starts immediately when the creator joins (1 human + 3 bots)
- `num_bots=0`: game waits for 4 humans before starting (pure PvP)
- `num_bots=1` or `num_bots=2`: game waits for the required number of humans, then fills remaining seats with bots

### API flow

1. Client calls `POST /games` on lobby with `{"num_bots": N}` (defaults to 3)
2. Lobby selects a healthy game server
3. Lobby generates game ID and calls `POST /games` on game server with `num_bots`
4. Game server creates empty game with specified bot count
5. Lobby returns WebSocket URL to client
6. Client connects to `ws://game-server/ws/{game_id}`
7. Client sends `join_game` message with player name
8. Game starts when the required number of humans have joined

Each human player in the game has independent bank time managed by per-player timers.

### Disconnect-to-bot replacement

When a human player disconnects from a started game, they are replaced with a bot instead of ending the game. The bot takes over the disconnected player's seat and continues playing. An application-level heartbeat (ping/pong) monitors client liveness; if no ping is received within 30 seconds, the server disconnects the client and triggers bot replacement. When the last human disconnects, the game is cleaned up (no all-bot games run without observers).

### Round Advancement

After a round ends, the server enters a waiting state. Human players must send a `confirm_round` action (or a 15-second timeout fires) before the next round begins. Bot seats are auto-confirmed. This allows clients to display round results before advancing.

### Web UI flow (client SPA on port 3000)

1. User opens `http://localhost:3000` which loads the SPA
2. Hash-based router renders lobby view at `#/`
3. Lobby view fetches games via `GET /games` (CORS-enabled on lobby server)
4. User clicks "Create Game" or "Join" on an existing game
5. Client stores WebSocket URL and player name in sessionStorage
6. Router navigates to `#/game/<id>` and renders game view
7. Game view connects via WebSocket using MessagePack binary frames
8. Client sends `join_game` message and displays all server messages in a log panel

## Web UI

- **Client** (`client/`, port 3000) - Primary frontend. TypeScript + SASS single-page application served by Bun's dev server. Uses lit-html for templating, hash-based routing (`#/` for lobby, `#/game/:id` for game), and MessagePack for WebSocket communication. Entry point is `client/index.html`.

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
│       ├── views/
│       │   ├── lobby.ts        # Lobby view (list/create games)
│       │   └── game.ts         # Game view (WebSocket log panel)
│       └── styles/
│           ├── main.scss       # SASS entry point (imports partials)
│           ├── _variables.scss # Shared design tokens
│           ├── _reset.scss     # CSS reset
│           ├── _layout.scss    # Shared layout and button styles
│           ├── _lobby.scss     # Lobby view styles
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
│   └── shared/                 # Shared code (future use)
```

## Running Locally

Requires [uv](https://docs.astral.sh/uv/) for Python package management and [Bun](https://bun.sh/) for the TypeScript client. Dependencies are installed automatically when running commands.

```bash
# Run all servers together (recommended for local testing)
make run-all

# Or run servers separately:
make run-game      # Game server on port 8001
make run-lobby     # Lobby server on port 8000
make run-client    # Client dev server on port 3000
```

Using the Web UI:
1. Run `make run-all` to start all servers
2. Open http://localhost:3000 in your browser
3. Create or join a game from the lobby view
4. Game view connects via WebSocket and displays server messages in a log panel

Using the API directly:
```bash
# List available games
curl http://localhost:8000/games

# Create a game with 3 bots (default, starts immediately with 1 human)
curl -X POST http://localhost:8000/games

# Create a game with custom bot count (waits for required humans)
curl -X POST http://localhost:8000/games -H 'Content-Type: application/json' -d '{"num_bots": 1}'

# Response:
# {"game_id": "abc123", "websocket_url": "ws://localhost:8001/ws/abc123", "server_name": "local-1"}
```

## Development

```bash
make test              # Run all tests
make test-lobby        # Run lobby tests only
make test-game         # Run game tests only
make lint              # Check code style
make format            # Auto-format code
make typecheck         # Run Python type checking (ty)
make typecheck-client  # Run TypeScript type checking
make check-agent       # Run all checks (format, lint, typecheck, test, client typecheck)
```

## Next Steps

1. Add game state synchronization
2. Add authentication
3. Add persistence (game history, player stats)
