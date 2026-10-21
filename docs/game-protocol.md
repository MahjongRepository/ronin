# Game Server Protocol

The game server (`:8711`) wire protocol. The source of truth is `backend/game/messaging/types.py`
(client messages, session messages, error codes), `backend/game/wire/enums.py` and
`backend/game/messaging/wire_enums.py` (integer codes), and the `serialization_alias` keys on the
event models in `backend/game/logic/events.py` and `types.py`. The frontend mirror is
`frontend/src/shared/protocol/`.

## REST API

- `GET /health` — health check
- `GET /status` — `pending_games`, `active_games`, `capacity_used`, `max_capacity`
- `POST /games` — create a pending game (called by the lobby). Body: `game_id`, `players` (each
  `name`, `user_id`, `game_ticket`) and `num_ai_players` (0–3, default 3). Every player's game ticket
  is verified (signature, expiry, `game_id` binding, identity) before the game is created.

`num_ai_players` sets how many humans the game waits for (`4 - num_ai_players`). The game starts
when they have all sent `JOIN_GAME`, or after the pending timeout (default 10s) with AI players in
the missing seats; if no human joined, the game is cancelled.

## WebSocket

Connect to `/ws/{game_id}` after the lobby has created the game. `game_id` comes from the path, not
from messages. Frames are binary MessagePack only.

Limits per connection:

- Rate limit: token bucket, 50 messages/s sustained, burst 80; excess messages get a `rate_limited`
  error and are dropped.
- 5 consecutive undecodable messages close the connection with code 4004.
- A connection that has not sent `JOIN_GAME` or `RECONNECT` within 10s is closed with code 4001.
- A provably invalid game action closes the connection with code 1008 and an AI player takes the
  seat.

### Client → server

Every client message carries an integer `t` (`WireClientMessageType`):

| `t` | Message    | Fields                             |
|-----|------------|------------------------------------|
| 3   | game action | `a` (action code), action fields  |
| 4   | chat       | `text` (1–1000 chars, no control characters) |
| 5   | ping       | —                                  |
| 6   | reconnect  | `game_ticket`                      |
| 7   | join game  | `game_ticket`                      |

Game actions (`a`, `WireGameAction`):

| `a` | Action        | Fields                                           |
|-----|---------------|--------------------------------------------------|
| 0   | discard       | `ti` (tile id, 0–135)                            |
| 1   | declare riichi | `ti`                                            |
| 2   | declare tsumo | —                                                |
| 3   | call ron      | —                                                |
| 4   | call pon      | `ti`                                             |
| 5   | call chi      | `ti`, `sequence_tiles` (the two tiles from hand) |
| 6   | call kan      | `ti`, `kan_type` (`open` / `closed` / `added`)   |
| 7   | kyuushu kyuuhai | —                                              |
| 8   | pass          | —                                                |
| 9   | confirm round | — (sent after `round_end`)                       |

```json
{"t": 7, "game_ticket": "<signed-ticket>"}
{"t": 3, "a": 0, "ti": 42}
{"t": 3, "a": 5, "ti": 40, "sequence_tiles": [44, 48]}
{"t": 3, "a": 9}
```

### Server → client: session messages

Session messages carry a string `type`:

- `{"type": "player_left", "player_name": "..."}` — broadcast to the other players
- `{"type": "game_left"}` — sent to the player who left
- `{"type": "chat", "player_name": "...", "text": "..."}`
- `{"type": "pong"}`
- `{"type": "game_reconnected", "gid": ..., "s": ..., "p": [...], ...}` — full state snapshot for
  the reconnecting seat (compact keys, see `ReconnectionSnapshot`)
- `{"type": "player_reconnected", "player_name": "..."}` — broadcast to the other players
- `{"type": "session_error", "code": "...", "message": "..."}`

Error codes (`SessionErrorCode`):

- `already_in_game`, `not_in_game`, `game_not_started`, `invalid_message`, `action_failed`,
  `rate_limited`, `invalid_ticket` (bad, expired or wrong-game ticket)
- `join_game_not_found` (no such pending game), `join_game_already_started` (use `RECONNECT`),
  `join_game_no_session`
- `reconnect_no_session`, `reconnect_no_seat`, `reconnect_game_gone`, `reconnect_game_mismatch`,
  `reconnect_already_active`, `reconnect_snapshot_failed`, `reconnect_retry_later` (transient: the
  game is starting, retry shortly)

### Server → client: game events

Game events are flat messages with an integer `t` (`WireEventType`) and compact alias keys:

| `t` | Event           | `t` | Event          |
|-----|-----------------|-----|----------------|
| 0   | meld            | 6   | dora_revealed  |
| 1   | draw            | 7   | error          |
| 2   | discard         | 8   | game_started   |
| 3   | call_prompt     | 9   | round_started  |
| 4   | round_end       | 10  | game_end       |
| 5   | riichi_declared | 11  | furiten        |

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

- `game_started` carries player names and AI flags once; later events identify players by seat.
- `round_started` is sent per seat with that seat's view.
- `draw` and `discard` pack their fields into one integer `d` (`backend/game/messaging/compact.py`):
  draw `d = seat * 136 + tile_id`; discard `d = flag * 544 + seat * 136 + tile_id`, where `flag`
  encodes tsumogiri and riichi. A draw goes only to the drawing seat, with `aa` (available actions)
  when it has any.
- No draw follows a pon or chi; the caller (from the meld event) is the next to discard.
- `meld` carries one IMME integer `m` (`backend/shared/lib/melds/README.md`).
- `call_prompt` is split per seat: a seat that can both ron and call a meld gets only the ron
  prompt.
- `round_end` inlines the round result, with `rt` as the result type (`WireRoundResultType`).
- `furiten` is sent only to the affected seat.

## Replay files

Replays are gzip-compressed NDJSON at `{replay_dir}/{id[0:2]}/{id[2:4]}/{game_id}.txt.gz`: a version
line `{"version": REPLAY_VERSION}` (`backend/game/replay/models.py`), then the broadcast events plus
each seat's draws (without `aa`). `game_started` gains the seed (`sd`) and RNG version (`rv`), and
the per-seat `round_started` views are merged into one record that holds every hand. The lobby serves them at `GET /api/replays/{game_id}`.
