# Game protocol (client side)

The client mirror of the game server's wire protocol (`backend/game/messaging/AGENTS.md`); a protocol change lands
here and in the backend in the same change.

- `parseServerMessage` is the single inbound entry and returns an `[error, message]` tuple; the per-message parsers
  under it throw. `parseReplayLine` is the replay file's entry.
- A schema requires what its consumer needs rather than defaulting it, so an incomplete message fails to parse. This
  includes the reconnect snapshot, which parses only whole.
- An offer parses only as an action or call the client knows, in the server's shape: an unknown one fails its whole
  message (a loss of step), never a turn offering less than the server's.
- Live and recorded parsing stay distinct: a field the live socket always stamps (seat, timers, wait id, bank) is
  required live even though a replay reads it as null. A replay's riichi cost and stick value come from its recorded
  settings, never client defaults.
- A live wait id belongs to the recipient alone: it increases for that participant's new decisions, round confirms
  included, and repeats on a resend. A snapshot carries the latest id even when nothing is owed; other seats' waits
  never advance it. Never compare ids across seats or interpret them as the engine's global progress.
- Tile id, copies and seat distance are spelled once, in `tiles.ts`.
