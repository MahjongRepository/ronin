# Game protocol (client side)

The client mirror of the game server's wire protocol (`backend/game/messaging/AGENTS.md`); a
protocol change lands here and in the backend in the same change.

* Wire values are `as const` objects with derived union types in `constants.ts`, not TS enums.
* `schemas/` parse every server message with Zod from compact wire keys into camelCase objects;
  `decoders/` unpack the integer draw, discard and IMME meld encodings; `builders/` construct every
  client message.
* `parseServerMessage` routes by `type` (session messages) or integer `t` (game events) and returns
  an `[error, message]` tuple, checked before the value is used. Follow that shape for new parsers.
