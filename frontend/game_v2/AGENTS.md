# Game client v2 (TypeScript / lit-html)

Served on every game page. Adapt the client to the server, never the server to it.

Rules per part: `src/entities/client/` (dispatcher, what the seat owes, desync, live board), `src/entities/session/`,
`src/entities/table/`, `src/entities/replay/`, `src/shared/protocol/`, `src/views/`, `src/styles/` (board layout).
The board's look is `docs/game-client-look.md`; where it and any `AGENTS.md` or the gate disagree, the spec wins.

## Architecture

* **One dispatcher.** The live game, the replay and scenarios all run on `entities/client`'s pure
  `(state, event) → { state, effects }` transitions. They never run IO, read a clock or start a timer: they return
  `ClientEffect`s, and only the live driver (`views/game.ts`) executes them. Pending deadlines live in the state; the
  driver keeps one timer armed to `nextDeadline`, which comes back as a tick, and a tick before a deadline does
  nothing. Every event carries logical time; the state's `now` never runs back.
* **One immutable client state**, a discriminated union where a field's absence never stands in for a variant: a
  replay's state has no session, viewer or sync, so nothing live can be asked of it. Read what the seat owes through
  `decisionOf`, `roundConfirmOf`, `desyncOf`.
* **Timelines, not history.** Stepping back selects an earlier state from `buildClientTimeline`, never an inverse
  event, and a timeline executes no effect, so revisiting a prompt sends nothing.
* **One clock.** Every time the page reads is `browserClock`'s (`shared/clock`): wall time that never runs back,
  absorbing a wall clock set back and counting a forward jump as time that passed (a sleep pauses
  `performance.now` on several platforms, so a forward step cannot be told from one; the server's deadlines really
  passed). Views take it as `deps.clock`; a test gives them `steadyClockOn` a `ManualClock`.
* **Views are controller instances, one per mount.** `index.ts` and the lazy `replay-entry.ts` wire the browser's sources (socket factory,
  loader, clock, storage). A view keeps no module state, looks up no element by id, takes input only through its own
  root, and its dispose cancels every timer, socket, fetch and listener it owns; a callback after dispose is dropped.
* **Components take faces, mappers take ids.** `Hand`, `Discards`, `Meld` take `TileFace`s; `GameBoard` renders a
  `BoardDisplayState` and decides nothing. A new board prop or panel is added to the mappers
  (`tableStateToDisplayState`, `tablePanel`, `playDisplay`, `replayDisplay`), never computed in a view or component.
  Every playable tile is a native button whatever its state.
* A new route also needs its path in the lobby's game page list (`backend/lobby/server/app.py`), which 404s others.
  The replay is a lazy route. Storybook routes, fixtures and styles are development-only and the
  production build rejects their modules, markup and styles, and any replay-only module reachable through an
  entry's static imports. `npm run build:dev` builds storybooks into `dist-dev/` for visual checks;
  `npm run build` keeps `dist/` production-only.
  Pico form rules and theme tokens, non-button links and the board debug overlay belong to the storybook stylesheet.
* `package.json` `sideEffects` lists every module with an import-time effect; a new one goes there or the build drops it.
* UI text is English literals; there are no catalogs. Game logic uses protocol codes and ids, never displayed text.

## Structure

Imports use `@/` for `src/`. Layers depend downward only: `views/` → `entities/` → `shared/`. Slices import each
other through their `index.ts`, downward only: `replay` → `client` → `session`, `table` → `tile`. `.oxlintrc.json`
enforces this with one `no-restricted-imports` override per layer and slice; a new slice needs its own override, and
since an override replaces the rule's options, each repeats the zod and test bans. A `shared/` module's `index.ts` is
a border too: code outside it imports `@/shared/<module>`, never its files (tests excepted, as for slices). Generic
lit-html helpers (focus, Tab inside a modal) are `shared/ui`'s. A helper two layers need goes to
the lowest layer allowed to hold it. `src/fixtures/` is generated data; only storybook views and tests import it.

## Conventions

* lit-html components are functions returning a `TemplateResult`; named exports only; no `console.log`.
* Styles: the locally maintained Pico subset in `src/assets/vendor/pico/`, dark scheme only
  (`styles/_pico.scss` assembles its modules; add styles there before using a new element).
  Every colour is a `--ronin-*` token from `styles/_theme.scss`, never a literal. Tile material is
  `styles/_tile.scss`'s alone. One face, `--ronin-font`; aligning figures take `type.figures` on their own numeric
  element. The font stack matches the lobby's system sans-serif stack; no font files are downloaded.
* Zod is `zod/mini` only (lint bans classic: it does not tree-shake and its JIT breaks the CSP). `zod-setup.ts` stays
  the first import of `index.ts`.
* Lint and format follow the lobby's config; keep them in sync. `new-cap` exceptions list this app's components.
* Supported floor: iOS Safari 16.4 and a 667x375 landscape phone. The rotate panel is a media query's choice alone;
  the session runs on under it.
* `npm run sprite` rebuilds the committed tile sprite after a tile SVG changes; never hand-edit it. The active tile
  set is `entities/tile/lib/tile-config.ts`'s alone.

## Tests

* Vitest. Tests live in `tests/` mirroring `src/` paths and import through `@/`; helpers in `tests/fixtures/` through
  `#tests/`. `describe` names the subject, `it` says what it pins; no doc or file-header comments.
* Build protocol events with the factories in `tests/fixtures/`, never repeated literals. Session and dispatcher tests
  are sequences of client events with the effects each returns, never through the DOM; view tests inject fakes, never
  mock modules.
* `src/fixtures/seat-scenarios/` and `src/fixtures/replays/` are generated, never edited by hand:
  `make generate-seat-scenarios` / `make generate-replay-fixtures` from `backend/scripts/seat_scenarios/` and
  `backend/scripts/replay_fixtures/`; the `*-check` gates fail on drift. A new interaction or replay case is a new
  backend scenario. Seat-scenario tests assert named checkpoints (decision, table, result), not effects alone. What
  the server cannot produce (client intents, ticks, switch sends, races) is a hand-written branch in
  `tests/fixtures/seat-transcripts.ts`.

## Visual check

A targeted check, not a gate: no `make` target, not in `make run-all-checks`. It shoots and checks only the pages and
viewports a run names (WebKit for phones, Chromium otherwise), with no backend:
`npm run visual-check -- --page <name> --viewport <name> --shots <dir>` (repeatable, substring match). Name the
changed area and its one worst case, never a sweep. A run over 60 pages is refused unless it passes `--many`; it checks
three pages at a time, one engine after the other, to keep a laptop cool.

* A new page or check goes in its surface's module under `scripts/visual-check/surfaces/`, never the runner.
* The check holds a few of the spec's proportions (`DERIVED` in `surfaces/board.ts`); change the spec's table and
  the check together.
* A board state worth checking at phone size is a story (`/play/storybook/decisions?state=<story>`), not a
  hand-written board. A passing check says nothing about clarity or hierarchy.
