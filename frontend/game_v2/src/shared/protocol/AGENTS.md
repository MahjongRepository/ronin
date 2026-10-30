# Game protocol (client side)

The client mirror of the game server's wire protocol; `backend/game/messaging/AGENTS.md` routes to
the protocol's source files, and a protocol change lands here and in the backend in the same change.

- `constants.ts` holds the wire values; `schemas/` parse every server message with Zod (`zod/mini`'s functional API) from compact
  wire keys into camelCase objects; `decoders/` unpack the packed integer draw, discard and IMME
  meld values; `builders/` construct every client message.
- `parseServerMessage` is the single entry for inbound messages and returns an `[error, message]`
  tuple that callers check before using the value. The per-message parsers under it throw on a bad
  payload and rely on that wrapper, so a new parser throws too rather than returning its own tuple.
- A schema requires what its consumer needs rather than defaulting it, so an incomplete message
  fails to parse. The reconnect snapshot parses only whole, as the server's builder sends it: each
  seat's player and state once, in seat order, each state's melds its own and its closed count one a
  turn leaves beside them (13 or 14, less 3 a meld), the viewer's own tiles as many as its count,
  each once, and a round history of every finished round (`n` deals before the one shown, plus that
  one once its result is pending). A score map (`wireScoreMapSchema`) names every seat, as the
  server's always do. A compact meld parses only within the decoder's range
  (`compactMeldSchema`), which is every value it unpacks because its meld ranges are contiguous.
- A replay file's event lines go through `parseReplayLine` instead, which also reads the replay-only
  lines (`REPLAY_LINE_TYPE`) the live socket never sends and defers every other line to
  `parseServerMessage`. Fields only the live socket stamps (viewer seat, timers, wait ids, banks,
  elapsed seconds) parse as optional and read as null in a replay. A replay's `game_started` carries no
  riichi cost (`rc`): `parseReplayLine` gives it the one its recorded settings (`gs.riichi_cost`) name.
