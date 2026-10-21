# Frontend (TypeScript / lit-html)

Before planning work here, read `frontend-architecture.md` (the two apps, routes, styles and module
structure).

@frontend-architecture.md

## Tooling

Bun drives everything, from `frontend/` or through the root `make` targets:

* `bun run typecheck` (`tsc --noEmit`), `bun run lint` (oxlint with warnings denied, stylelint, a
  Sass compile check), `bun run fmt` (oxfmt), `bun run test` (Vitest with coverage).
* `bun run sprite` regenerates the tile sprite after a tile SVG changes.

## Structure

Two apps share one source tree: the lobby scripts (`src/lobby/`, loaded by the server-rendered
pages) and the game client SPA (`src/index.ts` → `src/router.ts` → `src/views/`). Imports use the
`@/` alias for `src/`. Layers depend downward only, and follow the existing tree rather than
introducing new FSD layers:

* `views/` and `lobby/` — route views and lobby page scripts; they compose entities and shared code
  and never import each other.
* `entities/` — domain UI and models (`tile`, `table`), imported through each slice's `index.ts`.
  `table` may use `tile`, never the reverse.
* `shared/` — protocol, session, WebSocket and config; imports nothing above it.

## Conventions

* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Wire data is parsed with the Zod schemas in `shared/protocol/`; `parseServerMessage` returns an
  `[error, message]` tuple, checked before the value is used. Follow that shape for new parsers.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.

## Tests

Vitest with `happy-dom`. UI tests render lit templates into a DOM element and assert on the
result; logic tests call the module directly. New tests go in a `__tests__/` directory beside the code.
