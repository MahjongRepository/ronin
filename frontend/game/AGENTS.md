# Game client (TypeScript / lit-html)

The game client SPA under `/play/*`, built by Vite with Bun. `src/shared/protocol/` and
`src/entities/table/` have their own `AGENTS.md`.

## Build

* `index.html` is the app's page and `src/index.ts` its entry. Vite builds with base
  `/game-assets/`; the lobby answers the game pages with `dist/index.html` and serves `dist/` under
  `/game-assets/`, or proxies both to this app's Vite dev server under `make run-local-server`
  (`frontend/AGENTS.md`, Tooling).
* `bun run sprite` rebuilds the tile sprite from the tile SVGs after one changes; the sprite is
  committed. `entities/tile/lib/tile-config.ts` is the single source for the active tile set.

## App

* **Routes** (`src/index.ts` → `router.ts` → `views/`): pathname routes for the live game, the
  replay (loaded over HTTP) and the storybook component showcase. Each route may register a cleanup
  the router runs on navigation. The lobby lists each game page path with its login policy
  (`backend/lobby/server/app.py`) and 404s any other, so a new route needs its path added there.
* **Handoff:** the lobby stores the game socket URL and ticket per game (`shared/session/`, key and
  shape in `docs/architecture.md`) and navigates here; the client joins with the ticket and, after a
  disconnect, reconnects with backoff and resumes the seat with the same ticket. A "retry later"
  reconnect error is retried; every other reconnect error sends the player back to the lobby.
* **Silence watchdog:** the client sends nothing on its own, so a socket whose peer vanished never
  fires `onclose`. `GameSocket` therefore treats a server silent longer than any legitimate wait as
  a disconnect, measured on the wall clock so the first check after a device wake sees the whole
  gap. The limit is hand-derived from the session `TimerConfig` defaults
  (`backend/game/session/AGENTS.md`, Pacing) plus a margin for late timers; re-derive it when the
  pacing changes.

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree
rather than introducing new FSD layers:

* `views/` — route views; they compose entities and shared code.
* `entities/` — domain UI and models (`tile`: tiles, hands, melds, discards and the tile-id
  helpers; `table`: the game table model and board UI), imported through each slice's `index.ts`;
  `table` may use `tile`, never the reverse.
* `shared/` — protocol, session, WebSocket and config; imports nothing above it.

## Conventions

* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Styles: Pico CSS v2 (`styles/_pico.scss`) styles semantic HTML; add classes only for
  project-specific components. Use the `--ronin-*` tokens from `styles/_theme.scss` rather than
  literal colors and fonts. `styles/game-app.scss` is the one entry stylesheet; board layout lives
  in `styles/game-board/`.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.
* Zod runs jitless (`zod-setup.ts`): its JIT uses `new Function()`, which the game pages' CSP
  blocks. `zod-setup.ts` stays the first import of `index.ts`, ahead of any module that builds a
  schema.

## Tests

Vitest. UI tests render lit templates into a DOM element and assert on the result; logic tests call
the module directly. New tests go in a `__tests__/` directory beside the code. The `describe` block
names the subject (the module or function under test) and the `it` title says what it pins; tests
carry no doc comments, and source files carry no file-header comment.
