# Game client v2 (TypeScript / lit-html)

The earlier game client SPA, restored as the foundation of a future client: the lobby serves it
instead of `frontend/game/` on any game page whose query has `v=2` (`/play/{game_id}?v=2`,
`/play/history/{game_id}?v=2`). Its protocol layer parses the current protocol and replay format,
but the views act on far less of it than v1 does: no countdowns, decisions or robbed kans yet.
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
  replay (loaded over HTTP) and the storybook component showcase. A route mounts into the app's
  host element and returns its unmount, which the router runs before the next route mounts. The
  lobby lists each game page path with its login policy (`backend/lobby/server/app.py`) and 404s
  any other, so a new route needs its path added there.
* **Views are controller instances, one per mount.** A view is given its host, its sources and
  sinks (the socket factory, the replay loader, the handoff and the navigation) and its clock;
  `index.ts` is the one place that wires the browser's. A view keeps no module state, looks up no
  element by id and renders one top-level template into its host. Its input is its own: keys reach
  it only through its own focusable root, and a click outside closes only its own dropdown, so two
  mounts never move together. Its dispose cancels every timer, socket, fetch and listener it owns
  and clears its host, and a callback that still fires afterwards is dropped. The game view's
  driver ends the client as failed, on the page, when a step or an effect throws, rather than
  leaving its queue stuck, and reports a socket factory that throws as a failed connection.
* **One dispatcher over client events.** The live game runs on `entities/client`'s dispatcher, a
  pure `(state, event) → { state, effects }` over an explicit client event union: the raw wire
  payload of a server message (parsed inside, through `parseServerMessage`), the transport's open,
  close (with code and reason) and error, a logical time tick, and a local user intent. Every event
  carries the logical time its source stamped, and the state keeps the last one as its `now`, so a
  state kept at a historical cursor keeps its time. The transitions never run IO, read a clock or
  start a timer: they return effect descriptions of real IO only (open or close the socket, send,
  clear the handoff, leave for the lobby, report an unparseable message), and only the live driver
  (`views/game.ts`) executes them, so a scripted scenario steps the same dispatcher and asserts its
  effects. Timers are not effects: the state holds its pending deadlines, `nextDeadline` derives
  the earliest, and the driver keeps one timer armed to it that comes back as a tick. A tick before
  a deadline, or with none, does nothing, so a stale timer cannot act. Table and decision state
  join this dispatcher, not a second one; display-only data (the game view's debug log) stays in
  the view, out of the state.
* **Session** (`entities/session`): one machine owns joining, playing, reconnecting and the end.
  It joins with the lobby's ticket (`shared/session` holds the handoff) and resumes the seat with
  the same ticket. Two retries stay distinct, each with its own backoff and budget: a transport
  retry reopens a dropped socket, a session retry resends RECONNECT on the open socket after
  `reconnect_retry_later` (honoured only while reconnecting) or a rate limit on its JOIN_GAME or
  RECONNECT (only before the seat is held). A drop supersedes a waiting session retry, since the
  reopened socket sends RECONNECT itself. The stop policy follows the server: the 4002 and 1008 closes, a
  refusal that means the ticket will never hold the seat again, and a spent retry budget end the
  session, cancel its retry and send the player to the lobby; a game end ends it on the page; any
  other close is retried, 1000 included (`docs/architecture.md`, Game client contract). An ended
  session ignores everything after, except that leaving still goes to the lobby from an end that
  stayed on the page (a game end or a failure).
* **Silence watchdog:** the client sends nothing on its own, so a socket whose peer vanished never
  fires `onclose`. `GameSocket`, the socket's thin IO adapter (one connection attempt per
  instance; it never reconnects), therefore reports a server silent longer than any legitimate
  wait as a close, measured on the wall clock so the first check after a device wake sees the whole
  gap. The limit is hand-derived from the session `TimerConfig` defaults
  (`backend/game/session/AGENTS.md`, Pacing) plus a margin for late timers; re-derive it when the
  pacing changes.

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree
rather than introducing new FSD layers:

* `views/` — route views; they compose entities and shared code.
* `entities/` — domain UI and models (`tile`: tiles, hands, melds, discards and the tile-id
  helpers; `table`: the game table model, the replay file reader and the board UI; `session`: the
  session machine; `client`: the dispatcher over client events), imported through each slice's
  `index.ts`. A slice uses only slices below it: `client` may use `session` and `table`, `table`
  may use `tile`, never the reverse.
* `shared/` — protocol, handoff storage, the socket adapter, the replay fetch, the clock, config and
  small helpers; imports nothing above it.

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
module whose tests need different file-level `vi.mock`s gets a second, suffixed file.
`tsconfig.json` includes `tests`, so `npm run typecheck` checks them like `src`. Test helpers live in `tests/fixtures/` and are imported
through the `#tests/` subpath import (`package.json` `imports`), since a relative parent import
fails lint. Build protocol events with the event factories there, typed by the schemas' output,
rather than as literals repeated across tests, so a schema change fails the typecheck and is fixed
in one place. Raw wire payloads for the dispatcher live there too, as does the scenario stepper:
session and dispatcher tests are written as sequences of client events with the effects each step
returns, never through the DOM, and a view's own tests inject fakes for its socket factory, loader
and clock rather than mocking modules.

The replay files under `tests/fixtures/replays/` are generated, never edited by hand:
`make generate-replay-fixtures` records each from a game the engine plays
(`backend/scripts/replay_fixtures/`), and the checks fail when one drifts from what the engine
records now. A new replay case is a new scenario there. Tests load them through the fixtures'
loader, which parses them as the replay view does, and the model's tests assert outcomes on them,
not only that they run: literals for what the model computes, and a field the model passes through
compared with the event it came from.

The `describe` block names the subject (the module or function under test) and the `it` title says
what it pins; tests carry no doc comments, and source files carry no file-header comment.
