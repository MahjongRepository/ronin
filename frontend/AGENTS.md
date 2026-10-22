# Frontend (TypeScript / lit-html)

Two apps from one source tree, built by Vite with Bun: the lobby scripts that enhance the
server-rendered lobby pages, and the game client SPA. `src/shared/protocol/` and
`src/entities/table/` have their own `AGENTS.md`.

## Tooling

Bun drives everything, from `frontend/` or through the root `make` targets:

* `bun run typecheck` (`tsc --noEmit`), `bun run lint` (oxlint with warnings denied, stylelint, a
  Sass compile check), `bun run fmt` (oxfmt), `bun run test` (Vitest with coverage).
* `bun run sprite` rebuilds `src/assets/tiles/sprites/<set>.svg` from the tile SVGs after one
  changes; the sprite is committed. `entities/tile/lib/tile-config.ts` is the single source for the
  active tile set and tile size.
* Vite has two entries, `src/index.ts` (game) and `src/lobby/index.ts` (lobby), with
  `base: "/game-assets/"` for builds (`/` under the dev server). The lobby backend reads `dist/.vite/manifest.json` into template globals;
  under `make run-local-server` (`LOBBY_VITE_DEV_URL`) the templates load from the Vite dev server
  (`:5173`) instead.

## Apps

* **Lobby** (`src/lobby/`): no routing; the Jinja2 templates in `backend/lobby/views/templates/` are
  the pages and `lobby/index.ts` loads on all of them, starting what the page holds: the room
  (`#room-app`, `data-room-id`, `data-ws-url`), the matchmaking queue (`#matchmaking-app`), the
  history copy-link buttons. `lobby-socket.ts` is the JSON lobby WebSocket; it neither reconnects
  nor watches for a silent server.
* **Game client** (`src/index.ts` → `router.ts` → `views/`): pathname routes `/play/{gameId}`
  (live game), `/play/history/{gameId}` (replay over HTTP) and `/play/storybook[/...]` (dev
  component showcase). Each route may register a cleanup the router runs on navigation.
* **Handoff:** on `game_starting` the room or matchmaking script stores the WebSocket URL and game
  ticket with `storeGameSession` (`shared/session/`, sessionStorage keyed by game id) and navigates
  to `/play/{gameId}`. The game view sends `JOIN_GAME`; after a disconnect, or a server silent
  longer than any legitimate wait, `GameSocket` reconnects with backoff (10 attempts, 30s cap) and the view sends `RECONNECT` with the same
  ticket. `reconnect_retry_later` is retried; other reconnect errors send the player back to the
  lobby.
* **Silence watchdog:** the client sends nothing on its own, so a socket whose peer vanished (a FIN
  lost while the device slept) never fires `onclose`. `GameSocket` therefore treats 90s without a
  server frame as a disconnect, checked every 5s against the wall clock so the first check after a
  wake sees the whole gap. The longest legitimate silence towards one seat is about 75s: a call
  prompt to another seat (5s), that seat's full turn at the bank cap (5s base + 60s bank), then a
  chankan prompt for its added kan (5s); the margin covers late timers. The limit is tied to the
  session `TimerConfig` defaults (`backend/game/session/AGENTS.md`, Timers).

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree
rather than introducing new FSD layers:

* `views/` and `lobby/` — route views and lobby page scripts; they compose entities and shared code
  and never import each other.
* `entities/` — domain UI and models, imported through each slice's `index.ts`. `tile`: `Tile`,
  `Hand`, `Meld`, `Discards` and the 136-format tile helpers. `table`: the game table model and
  board UI. `table` may use `tile`, never the reverse.
* `shared/` — protocol, session, WebSocket and config; imports nothing above it.

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
* Zod runs jitless (`zod-setup.ts`): its JIT uses `new Function()`, which the CSP `script-src 'self'`
  blocks. `zod-setup.ts` stays the first import of `index.ts`, ahead of any module that builds a schema.

## Tests

Vitest with `happy-dom`. UI tests render lit templates into a DOM element and assert on the
result; logic tests call the module directly. New tests go in a `__tests__/` directory beside the code.
Tests carry no doc comments: the `it(...)` title says what it pins. Source files carry no file-header
comment.
