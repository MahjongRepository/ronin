# Lobby Server API

The lobby server (`:8710`) routes and WebSocket protocols. The source of truth is the route table in
`backend/lobby/server/app.py` and the message models in `backend/lobby/rooms/` and
`backend/lobby/matchmaking/`.

## Routes

Public:

- `GET /login`, `POST /login`, `GET /register`, `POST /register` (auto-login), `POST /logout`
- `GET /health`
- `GET /play/history/{game_id}` — the game client page in replay mode
- `GET /api/replays/{game_id}` — gzip NDJSON replay (`Content-Encoding: gzip`, immutable cache);
  404 for an unknown id or one shorter than 4 characters
- `GET /play/storybook[/board|/discards|/hand|/melds]`, and `GET /storybook` in dev builds
- `/static/` (from `frontend/public/`) and `/game-assets/` (built client from `frontend/dist/`)

Protected (session cookie, or `X-API-Key` for bots):

- `GET /` — room list
- `GET /history` — the 20 most recent completed games with replay links
- `GET /matchmaking` — matchmaking queue page
- `GET /play/{game_id}` — game client page
- `POST /rooms/new` — create a room, 303 to `/rooms/{room_id}`
- `GET /rooms/{room_id}` — room page
- `POST /rooms/{room_id}/join` — check the room exists, redirect to it
- `GET /servers` — configured game servers with live health (JSON; 401 when unauthenticated)

Bot accounts only (403 for humans):

- `POST /api/auth/bot` — lobby session for joining a room by WebSocket
- `POST /api/rooms` — create a room; optional `min_human_players` (1–4, default 1); returns
  `room_id`, `session_id`, `ws_url`. Sending `num_ai_players` is a 400.
- `POST /api/matchmaking/join` — lobby session for the matchmaking queue; returns `session_id`,
  `ws_url`

WebSockets (cookie auth, or the `session_id` query parameter; `Origin` checked):

- `WS /ws/rooms/{room_id}`
- `WS /ws/matchmaking`

## Room WebSocket

JSON text frames. A room is a fixed 4-seat table: creating it fills every seat with a tsumogiri
bot, and each joining human replaces the first bot seat. The creator owns the room and starts the
game; nothing starts automatically.

Player objects, always 4 per `players` array in seat order (bot seats are always ready):

```json
{"name": "Alice", "ready": true, "is_bot": false, "is_owner": true}
```

Client → server:

- `{"type": "set_ready", "ready": true}` — non-owners only
- `{"type": "start_game"}` — owner only; allowed when at least `min_human_players` humans are seated
  and every non-owner human is ready
- `{"type": "chat", "text": "..."}`, `{"type": "leave_room"}`, `{"type": "ping"}`

Server → client:

- `room_joined` — `room_id`, `player_name`, `is_owner`, `can_start`, `players`
- `player_joined`, `player_left` — `player_name`, `players`, `can_start`
- `player_ready_changed` — `players`, `can_start`
- `owner_changed` — sent to the new owner: `is_owner`, `can_start`, `players`
- `chat` — `player_name`, `text`
- `game_starting` — `ws_url`, `game_ticket`, `game_id`, `game_client_url`
- `error` — `message`
- `pong`

## Matchmaking WebSocket

JSON text frames. Each connection joins a FIFO queue; when 4 players are queued the lobby creates a
game with no AI players and sends each of them `game_starting`. A user already in a room is
rejected with `already_in_room`, and a second connection from the same user with
`already_in_queue`.

- Client → server: `{"type": "ping"}`
- Server → client: `queue_joined` (`position`, `queue_size`), `queue_update` (`queue_size`),
  `game_starting` (same shape as the room message), `error` (`message`), `pong`

## Bots

Register a bot account (the API key is printed once and never stored):

```
cd backend && AUTH_DATABASE_PATH=storage.db uv run python -m scripts.register_bot <bot_name>
```

A bot sends its key as `X-API-Key`, takes `session_id` and `ws_url` from `POST /api/rooms` or
`POST /api/matchmaking/join`, and opens that WebSocket with `?session_id=...`. In a room it is the
owner in seat 0 and, with the default `min_human_players=1`, can send `start_game` at once. On
`game_starting` it connects to the game server and sends `JOIN_GAME` (`docs/game-protocol.md`).
