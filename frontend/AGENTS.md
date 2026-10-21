# Frontend (TypeScript / lit-html)

Two apps from one source tree, built by Vite with Bun: the lobby scripts that enhance the
server-rendered lobby pages, and the game client SPA. The wire protocol they speak is in
`docs/game-protocol.md` and `docs/lobby-api.md`.

## Tooling

Bun drives everything, from `frontend/` or through the root `make` targets:

* `bun run typecheck` (`tsc --noEmit`), `bun run lint` (oxlint with warnings denied, stylelint, a
  Sass compile check), `bun run fmt` (oxfmt), `bun run test` (Vitest with coverage).
* `bun run sprite` rebuilds `src/assets/tiles/sprites/<set>.svg` from the tile SVGs after one
  changes; the sprite is committed. `entities/tile/lib/tile-config.ts` is the single source for the
  active tile set and tile size.
* Vite has two entries, `src/index.ts` (game) and `src/lobby/index.ts` (lobby), with
  `base: "/game-assets/"`. The lobby backend reads `dist/.vite/manifest.json` into template globals;
  under `make run-local-server` (`LOBBY_VITE_DEV_URL`) the templates load from the Vite dev server
  (`:5173`) instead.

## Apps

* **Lobby** (`src/lobby/`): no routing; the Jinja2 templates in `backend/lobby/views/templates/` are
  the pages and `lobby/index.ts` loads on all of them, starting what the page holds: the room
  (`#room-app`, `data-room-id`, `data-ws-url`), the matchmaking queue (`#matchmaking-app`), the
  history copy-link buttons. `lobby-socket.ts` is the JSON lobby WebSocket with a 10s ping.
* **Game client** (`src/index.ts` → `router.ts` → `views/`): pathname routes `/play/{gameId}`
  (live game), `/play/history/{gameId}` (replay over HTTP) and `/play/storybook[/...]` (dev
  component showcase). Each route may register a cleanup the router runs on navigation.
* **Handoff:** on `game_starting` the room or matchmaking script stores the WebSocket URL and game
  ticket with `storeGameSession` (`shared/session/`, sessionStorage keyed by game id) and navigates
  to `/play/{gameId}`. The game view sends `JOIN_GAME`; after a disconnect `GameSocket`
  reconnects with backoff (10 attempts, 30s cap) and the view sends `RECONNECT` with the same
  ticket. `reconnect_retry_later` is retried; other reconnect errors send the player back to the
  lobby.

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree
rather than introducing new FSD layers:

* `views/` and `lobby/` — route views and lobby page scripts; they compose entities and shared code
  and never import each other.
* `entities/` — domain UI and models, imported through each slice's `index.ts`. `tile`: `Tile`,
  `Hand`, `Meld`, `Discards` and the 136-format tile helpers. `table`: the game table model and
  board UI. `table` may use `tile`, never the reverse.
* `shared/` — protocol, session, WebSocket and config; imports nothing above it.

## Protocol layer (`shared/protocol/`)

* Wire values are `as const` objects with derived union types in `constants.ts`, not TS enums.
* `schemas/` parse every server message with Zod from compact wire keys into camelCase objects;
  `decoders/` unpack the integer draw, discard and IMME meld encodings; `builders/` construct every
  client message.
* `parseServerMessage` returns an `[error, message]` tuple, checked before the value is used.
  Follow that shape for new parsers.
* A server protocol change lands here in the same change as the backend and `docs/game-protocol.md`.

## Table model (`entities/table/`)

The replay view runs on a pure model:

* `TableState` / `PlayerState` (`model/types.ts`) hold the table. `applyEvent(state, event)`
  returns a new state: no mutation, exhaustive dispatch ending in `assertNever`, and a handler
  throws on an impossible state (a missing tile or caller) instead of returning the state
  unchanged.
* `buildTimeline(events)` precomputes every state (`states[i + 1]` follows `events[i]`);
  `buildActionSteps` folds bookkeeping events (`dora_revealed`, `game_started`, the first draw of a
  round) into the preceding step; `buildNavigationIndex` maps steps to rounds and turns.
* `lib/board-mapper.ts` turns a `TableState` into the `BoardDisplayState` the `ui/` components
  render, rotating seats so the dealer sits at the bottom.
* `ReplayEvent` is the subset of events stored in replays; `call_prompt`, `error` and `furiten` never
  appear there.

## Conventions

* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Lobby page modules split like `lobby/room/`: `state.ts` (state and pure queries), `handlers.ts`
  (everything that reads or writes the socket, taking the state first), `ui.ts` (templates only,
  never the socket), `index.ts` (wiring). The server is authoritative: derive ready state, owner and
  `can_start` from its messages, don't keep a local copy.
* Styles: Pico CSS v2 (`styles/_pico.scss`) styles semantic HTML; add classes only for
  project-specific components. Use the `--ronin-*` tokens from `styles/_theme.scss` rather than
  literal colors and fonts. Each app has one entry stylesheet (`lobby-app.scss`, `game-app.scss`);
  board layout lives in `styles/game-board/`.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.

## Tests

Vitest with `happy-dom`. UI tests render lit templates into a DOM element and assert on the
result; logic tests call the module directly. New tests go in a `__tests__/` directory beside the code.
