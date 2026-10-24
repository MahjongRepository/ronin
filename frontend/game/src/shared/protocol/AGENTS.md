# Game protocol (client side)

The client mirror of the game server's wire protocol; `backend/game/messaging/AGENTS.md` routes to
the protocol's source files, and a protocol change lands here and in the backend in the same change.

- `constants.ts` holds the wire values; `schemas/` parse every server message with Zod from compact
  wire keys into camelCase objects; `decoders/` unpack the packed integer draw, discard and IMME
  meld values; `builders/` construct every client message.
- `parseServerMessage` is the single entry for inbound messages and returns an `[error, message]`
  tuple that callers check before using the value. The per-message parsers under it throw on a bad
  payload and rely on that wrapper, so a new parser throws too rather than returning its own tuple.
