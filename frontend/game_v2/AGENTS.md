# Game client v2 (TypeScript / lit-html)

The earlier game client SPA, restored as the foundation of a future client: the lobby serves it
instead of `frontend/game/` on any game page whose query has `v=2` (`/play/{game_id}?v=2`,
`/play/history/{game_id}?v=2`). Its protocol layer parses the current protocol and replay format,
but the views act on far less of it than v1 does: no countdowns, close codes or robbed kans yet.
Adapt the client to the server rather than the server to it. `src/shared/protocol/` and `src/entities/table/` have their own `AGENTS.md`.

## Build

* `index.html` is the app's page and `src/index.ts` its entry. Vite builds with base
  `/game-assets/v2/`; the lobby answers a `?v=2` game page with `dist/index.html` and serves `dist/`
  under `/game-assets/v2/`, or proxies both to this app's Vite dev server under
  `make run-local-server` (`frontend/AGENTS.md`, Tooling). The `v=2` parameter does not survive
  the client's own links, so open each page with it by hand.
* `npm run sprite` (Node runs the TypeScript script directly) rebuilds the tile sprite from the
  tile SVGs after one changes; the sprite is committed. `entities/tile/lib/tile-config.ts` is the
  single source for the active tile set.
* UI text is English literals; the app has no catalogs, so `bin/check_i18n.py` does not cover it.

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
* Lint and format follow the lobby's config (keep them in sync); the `.oxlintrc.json` overrides
  relax only rules the restored code trips where it is shaped by its domain: the socket's
  replaceable `on*` handlers, the nested Zod tuples of the wire schemas and the long event
  dispatchers.
* Zod runs jitless (`zod-setup.ts`): its JIT uses `new Function()`, which the game pages' CSP
  blocks. `zod-setup.ts` stays the first import of `index.ts`, ahead of any module that builds a
  schema.

## Tests

Vitest. UI tests render lit templates into a DOM element and assert on the result; logic tests call
the module directly. Tests live in `tests/`, outside `src/`, at the path of the module they cover
(`tests/entities/tile/hand.test.ts` for `src/entities/tile/hand.ts`), and import it through `@/`; a
module whose tests need different file-level `vi.mock`s gets a second, suffixed file
(`tests/views/replay-click-outside.test.ts`). `tsconfig.json` includes `tests`, so
`npm run typecheck` checks them like `src`. Test helpers live in `tests/fixtures/` and are imported
through the `#tests/` subpath import (`package.json` `imports`), since a relative parent import
fails lint. Build protocol events with the event factories there, typed by the schemas' output,
rather than as literals repeated across tests, so a schema change fails the typecheck and is fixed
in one place.

The replay files under `tests/fixtures/replays/` are generated, never edited by hand:
`make generate-replay-fixtures` records each from a game the engine plays
(`backend/scripts/replay_fixtures/`), and the checks fail when one drifts from what the engine
records now. A new replay case is a new scenario there. Tests load them through the fixtures'
loader, which parses them as the replay view does, and the model's tests assert outcomes on them,
not only that they run: literals for what the model computes, and a field the model passes through
compared with the event it came from.

The `describe` block names the subject (the module or function under test) and the `it` title says
what it pins; tests carry no doc comments, and source files carry no file-header comment.
