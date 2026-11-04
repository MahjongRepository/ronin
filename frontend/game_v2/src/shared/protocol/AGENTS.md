# Game protocol (client side)

The client mirror of the game server's wire protocol (`backend/game/messaging/AGENTS.md`); a protocol change lands
here and in the backend in the same change.

- Live frames use integer metadata map keys in both directions. `WIRE_KEY` is the one named ID
  registry; protocol code references its constants rather than raw numeric field IDs. IDs already
  used by replay storage never change when live fields are added. The shared Python/TypeScript
  golden pins the live contract.
- `encodeWireMessage` and `decodeWireMessage` own the live boundary. Message builders and schemas use `WIRE_KEY` directly; parsed domain models,
  handlers and UI keep readable field names. The codecs validate numeric metadata without translating aliases; score-map
  seats remain string data keys. Unknown, duplicate and incorrectly typed keys fail decoding before
  a message reaches its consumer. Replay-only fields are not live metadata.

- `parseServerMessage` is the single inbound entry and returns an `[error, message]` tuple; the per-message parsers
  under it throw. `parseReplayLine` is the replay file's entry.
- A schema requires what its consumer needs rather than defaulting it, so an incomplete message fails to parse. This
  includes the reconnect snapshot, which parses only whole.
- An offer parses only as an action or call the client knows, in the server's shape: an unknown one fails its whole
  message (a loss of step), never a turn offering less than the server's.
- Live and recorded parsing stay distinct: a field the live socket always stamps (seat, timers, wait id, bank) is
  required live even though a replay reads it as null. A replay's stick value and aka-dora flag come from explicit recorded viewing fields. Its compact rules reference stays opaque to the browser; no Python rules profiles are duplicated here.
- Live draws and draw notices carry no wall count; round starts and reconnect snapshots retain it. Recorded draws
  require their explicit count and parse with a distinct source discriminant, so the table does not invent replay data.
- A live wait id belongs to the recipient alone: it increases for that participant's new decisions, round confirms
  included, and repeats on a resend. A snapshot carries the latest id even when nothing is owed; other seats' waits
  never advance it. Never compare ids across seats or interpret them as the engine's global progress.
- Tile id, copies and seat distance are spelled once, in `tiles.ts`.
