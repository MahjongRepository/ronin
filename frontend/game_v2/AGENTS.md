# Game client v2 (TypeScript / lit-html)

The foundation of a future game client: the lobby serves it instead of `frontend/game/` on any game page whose query
has `v=2` (`/play/{game_id}?v=2`, `/play/history/{game_id}?v=2`). Its protocol layer parses the current protocol and
replay format; the live game plays its decisions on the board (the discard, the offers, pass, the countdown and
furiten) and the round results the player confirms, and the replay reads a recorded game. Adapt the client to the
server rather than the server to it.

Each part's rules are in its own `AGENTS.md`: `src/entities/client/` (what the seat owes, the loss of step, the live
board), `src/entities/session/`, `src/entities/table/`, `src/shared/protocol/`, `src/views/` (the live driver, the
replay page) and `src/styles/` (the board's layout).

## Build

* `index.html` is the app's page and `src/index.ts` its entry. Vite builds with base `/game-assets/v2/`; the lobby
  answers a `?v=2` game page with `dist/index.html` and serves `dist/` under `/game-assets/v2/`, or proxies both to
  this app's Vite dev server under `make run-local-server` (`frontend/AGENTS.md`, Tooling). The lobby never adds
  `v=2`, so open the first page with it by hand; the client's own links to its pages (another game's page, a game's
  replay) keep the page's query, and with it the parameter.
* `npm run sprite` (Node runs the TypeScript script directly) rebuilds the tile sprite from the tile SVGs after one
  changes; the sprite is committed. `entities/tile/lib/tile-config.ts` is the single source for the active tile set.
  The sprite ships as an asset of its own, cached apart from the code: `index.html` preloads it, `index.ts` fetches
  and injects it before the first route mounts, retrying a failed fetch with backoff and again when the browser comes
  back online (`loadTileSprite` over `shared/lib`'s `startRetryingLoad`, IO the entry owns), and a face drawn before
  it lands shows once it does. Until then each face shows its short name (`5m`, `E`), so a tile is never blank; the
  live game's board says so with a reload while a load has failed (`PlayUi`'s sprite status, which the driver keeps
  from the loader, never the dispatcher).
* The one face is Inter, self-hosted: `src/assets/fonts/inter-latin.woff2`, a Latin subset with its own tabular
  figures (how it was cut and from which release in `SOURCE.txt`, the licence in `OFL.txt` beside it). `_theme.scss`
  declares it with `font-display: swap`, so text never waits on it (a countdown reads at once), and `index.html`
  preloads it like the sprite, so it usually lands before a board does; a glyph outside the subset (a name in another
  script) falls back to the system sans-serif after it in `--ronin-font`.
* `package.json`'s `sideEffects` names the only modules with an import-time effect (the stylesheets, `zod-setup.ts`),
  so the build drops a module none of a route's code uses even when a barrel re-exports it: the replay's and the
  scenarios' modules stay out of the entry. A new module with such an effect is added there, or the build drops it.
* UI text is English literals; the app has no catalogs, so `bin/check_i18n.py` does not cover it.

## App

* **Routes** (`src/index.ts` → `router.ts` → `views/`): pathname routes for the live game, the replay (loaded over
  HTTP) and the storybook component showcase. A route mounts into the app's host element and returns its unmount,
  which the router runs before the next route mounts. The live game is the entry chunk; the replay and the storybook
  are lazy routes (`lazyRoute`), each a chunk of its own that brings its own stylesheet, so neither ships to a player
  who only plays. The lobby lists each game page path with its login policy (`backend/lobby/server/app.py`) and 404s
  any other, so a new route needs its path added there.
* **Views are controller instances, one per mount.** A view is given its host, its sources and sinks (the socket
  factory, the replay loader, the handoff, its lookup and the navigation) and its clock; `index.ts` is the one place
  that wires the browser's. A view keeps no module state, looks up no element by id and renders one top-level template
  into its host. Its input is its own: keys reach it only through its own focusable root, and a click outside closes
  only its own dropdown, so two mounts never move together. Its dispose cancels every timer, socket, fetch and
  listener it owns and clears its host, and a callback that still fires afterwards is dropped.
* **One dispatcher over client events.** The live game, the replay and scripted scenarios all run on
  `entities/client`'s dispatcher, pure `(state, event) → { state, effects }` transitions over an explicit client event
  union (`ClientEvent`), with one entry per client kind: a live seat's (`stepGameClient`, `traceLiveClient`) takes
  every event but a replay line (`LiveEvent`), server messages arriving as raw wire payloads parsed inside, beside the
  transport's events, logical time ticks and local user intents; a replay's (`traceReplayClient`) takes only its
  file's lines (`ReplayLineEvent`), raw JSON objects parsed inside. Every event carries the logical
  time its source stamped, and the state keeps the last one as its `now`, never running back (an event stamped
  earlier is taken at `now`), so a state kept at a historical cursor keeps its time. The transitions never run IO,
  read a clock or start a timer: they return descriptions of real IO only (`ClientEffect`), and only the live driver
  (`views/game.ts`) executes them. Timers are not effects: the state holds its pending deadlines, `nextDeadline`
  derives the earliest, and the driver keeps one timer armed to it that comes back as a tick. A tick before a
  deadline, or with none, does nothing, so a stale timer cannot act.
* A valid event the dispatcher otherwise ignores (a socket error, an intent with nothing to answer) is not a tick: it
  advances `now` and runs the expiry and the resync settlement every event runs, so it can send a resync request that
  came due, but only a tick drives the session's deadlines (a connect timeout, a retry). An event tag the client does
  not know is a bug, thrown as an ordinary error (`assertNever`); malformed wire input puts the client out of step
  through parsing, and a recognized message the table cannot take throws a `DesyncError`
  (`entities/client/AGENTS.md`, Desync). Display-only data (the game view's debug log) stays in the view, out of the
  state.
* **One client state.** The dispatcher composes the session, the table (`entities/table`) and the viewer's
  interaction into one immutable state, a union a field's absence never stands in for: a replay's client holds the
  table and its calls alone (no session, viewer, switches, notices or sync, so it takes only replay lines and nothing
  live can be asked of it), and a live seat's adds its session, its seat, furiten, timer settings, the first deal's
  due time, the play switches, the highest wait id opened, the notices, the game's last result shown and its sync. The
  sync is in step, holding what the seat owes, or out of step, holding the desync record and its failure count, so an
  out-of-step client owes nothing by construction. What the seat owes is one field, a decision or a round confirm,
  never both: a round end closes every decision and only the next deal opens one, and an opening replaces whatever
  was owed. The seat owes only while its session holds the seat (playing): every step ends by dropping it otherwise
  (`settledPending`), whether the socket dropped, the session ended or the server has not admitted the identity yet,
  since the server re-sends every wait it still owes after the admission and its snapshot says whether the confirm
  is. Read them through `decisionOf`, `roundConfirmOf` and `desyncOf`. The game's last result shown over the
  standings is not owed (it sends nothing) and survives a loss of step. Visibility (a replay's every hand, a live
  seat's own) is what the source showed and how the board is drawn, never a second model, and the seat at the bottom
  is the view's choice (the replay's is the recorded first dealer's, `docs/architecture.md`, Replays).
* **Timelines, not history in the driver.** `buildClientTimeline` steps any event sequence into the state after each
  event; stepping back selects an earlier state, never an inverse event, and nothing in a timeline executes an effect,
  so revisiting a prompt sends nothing and arms no timer. The replay view reads its file into such a timeline, and
  each of its stops is one of the timeline's states. Reading stops at the file's first line that does not parse or
  that the table refuses, since every later state would build on a table that missed it, and the page labels such a
  replay damaged, as it labels one whose recording ends before the game's end incomplete. The dispatcher takes one
  event in one step, except a replay's round end that robbed a kan, which the replay records no declaration line for:
  `traceReplayClient` takes that in two parts, the kan declared and then the result, each an entry of the timeline; a
  live seat sees the kan from its chankan prompt or the round end alone. A live game's own history review, if ever
  wanted, keeps the authoritative state moving forward apart from its cursor.
* **Components take faces, mappers take ids.** `Hand`, `Discards` and `Meld` take display tiles keyed by `TileFace` (a
  meld as the tiles `meldTiles` lays it out), never raw tile ids; the mappers convert. A hand tile keeps its tile id
  when it came from a table, and one of the viewer's own may be playable: selectable, selected, disabled or waiting.
  Every playable tile is a native button (focus, Enter and Space, a visible focus ring, a named action) whatever its
  state, so a turn never moves focus out of the hand; only a selectable one acts, the others carry `aria-disabled`
  (the selected one, the tile an answer played, `aria-pressed` too). The hand reports a pressed selectable tile's id
  and nothing else. Orientation stays with the board's strips, which rotate whole hands.
* **The board renders a display state; a mapper derives it.** `GameBoard` (`entities/table`) renders a
  `BoardDisplayState` with slots for an overlay, the local hand's input and a place by the hand for the decision's
  controls, and decides nothing. `tableStateToDisplayState` maps a table from a perspective; `playDisplay`
  (`entities/client`) maps a whole client state for the live board, offering exactly what the dispatcher takes. A new
  prop on the board is added to these mappers when a scenario shows the need, never computed in a view.
* One gesture serves every board (live, replay, storybook): hovering a nameplate, or tapping it (a button, so a key
  too), shows the other seats' scores in the centre as differences from its own; a tap pins it until it is tapped
  again, another part of the board is tapped or Escape is pressed. The replay's viewpoint switch is a control of its
  own, never the nameplate's tap.

## Layout

The board's target is `docs/game-client-look.md`, which wins where it and this section disagree; what follows holds
through the rebuild to it. The board's own placement rules are `src/styles/AGENTS.md`'s.

* **Browser floor: iOS Safari 16.4** (range media syntax; container queries need 16.0, `dvh` 15.4), and the smallest
  supported landscape is 667x375 (iPhone SE 2nd and 3rd generation): the 568x320 phones never got iOS 16.4, so they
  are below the floor. The board's sizing rule needs CSS `round()` (Chrome 125, Firefox 118, Safari 15.4) and
  `@property` (Safari 16.4).
* **The live game's page** is the board alone, its own controls in the board's corner (`entities/client/AGENTS.md`,
  The live board), so a phone gives the board its whole width.
* **Phone policy: the live game is played in landscape.** On an upright touch screen narrower than 600px
  (`(orientation: portrait) and (width < 600px) and (pointer: coarse)`, so a narrow desktop window is never told to
  rotate a phone), the game view shows the rotate panel (`entities/client`) in place of its play area. A media query
  alone chooses it: no Screen Orientation lock, which iOS Safari lacks. Both are rendered from the same state, so the
  socket, the session and its timers run on underneath. The server's timer never pauses for it, so a decision left
  unrotated can time out: an accepted cost. Replay and storybook pages take no timed input: they allow portrait and
  scroll rather than clip.
* **Visual gate:** `make visual-check` builds the app, checks the bundle budget, serves `dist/` with a replay fixture
  and a seat transcript over a mocked socket (no backend), and loads each surface's worst cases in Chromium and WebKit
  at the viewports each page names (`PageCase.at`, the 667x375 floor when it names none; the viewports are
  `scripts/visual-check/viewports.ts`'s). The gate selects representative worst cases (the densest board, the longest
  names and strings, the most melds, the densest results) across the floor in WebKit and 1440x900 and 2560x1440 in
  Chromium. Each further page/viewport combination exercises a distinct layout path or a denser form not already
  covered. Other states run once where they bind, or are omitted when a kept case covers the same elements and
  layout path in a harsher form. The runner fails a page naming no viewport or an unknown one, a viewport no page
  names, an unknown contrast viewport, and a contrast page at none. Its checks are the scripts'
  (`scripts/visual-check/`): the layout's geometry (nothing outside the board or the screen, nothing over a tile, a
  control, the action source or the panel it must clear, every tap target at least 40x40, text never under 10px, the
  own hand the board's largest tiles), the replay's and the live board's input and live regions, the panels' scroll
  and focus, the face's load, contrast at 4.5:1 for every text, mark and glyph on the contrast viewports, and any
  console error, failed request or missing element. Every request off the page's origin is answered empty, so the
  app's own face is the only one a capture draws. Each context asks for reduced motion, so a shot shows an
  animation's resting state; the stories that test real input timing (the replay's) run on the browser's clock. It
  writes a screenshot per page to `thoughts/screenshots/visual-check/`.
* A board state worth checking at phone size is a storybook state; one the generated scenarios reach is a decisions
  story rather than a hand-written one. It earns a page in the gate only by showing what no kept page does, and a
  viewport earns a place only by guarding a path of the layout no kept one reaches. `make install-frontend` installs
  the gate's Chromium and WebKit (`npx playwright install`, matching the pinned `playwright`); on a fresh Linux host
  their system libraries come from `npx playwright install-deps`, which needs root.
* On success `make visual-check` stamps a fingerprint of its inputs (every non-ignored file under `frontend/game_v2`,
  tracked or not, and the `Makefile`) in `node_modules/.cache/visual-check.pass`; `make run-all-checks` skips the gate
  only when the current fingerprint matches that stamp, so a skip always means these exact inputs passed. Run
  directly, it always runs. While iterating, `node scripts/visual-check/run.ts --page <name> --viewport <name> --shots
  <dir>` (after `vite build`; each repeatable, matching names by substring) checks and shoots only those pages: at
  the viewports they name with `--page` alone, at every viewport named, whether the page names it or not, when both
  are given (a change's before and after); it skips the replay load budget and never stamps.
* **The gate's structure** (`scripts/visual-check/`): the runner loads the pages and composes one module per surface,
  each declaring its pages and its checks, so a new page or check goes in its surface's module alone, never the
  runner or another surface. Every surface's board checks run on every page that draws a board, whichever surface's
  page it is, so each page is held to every surface's rules; a check across pages keeps what it compares in its own
  `PageRecord`, never on the shared report. Measurement shared by surfaces (boxes, the board's common geometry, text
  and the face, contrast) has its own modules; a surface measures what only it reads.
* **Budgets**, in the same run: `scripts/bundle-budget.ts` reads the manifest the gate's build alone writes (`vite
  build --manifest`; it deletes it, so `dist/` never serves one) and fails when a route loads more JavaScript or CSS
  than its budget, raw or gzipped (the game route is the entry and its static imports; a lazy route is what it adds;
  the tile sprite and the font have their own, and the cold start, the entry with both, is reported; the standings'
  chunk, which no route imports statically, has its own), the budgets set about a tenth over the measured sizes, a
  lazy route's CSS at least 1 KiB over. Then the replay load budget loads the largest engine replay fixture on the
  same server and Chromium, slowed sixfold (`Emulation.setCPUThrottlingRate`), and fails when the median of a few
  reads of the replay view's `replay-load` measure (parse, reduce into the client timeline, steps and navigation
  index, before the first render) exceeds its budget. A run counts only when its measure's detail shows it read the
  whole fixture (its stops, rounds, final standings, the game's end and no damaged line) in a finite time. The timing
  depends on the host's CPU, so the budget is set well above this host's median. Growing past a budget is a decision
  made in the script with the new measurement, not a drift.

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree rather than
introducing new FSD layers:

* `views/` — route views; they compose entities and shared code.
* `entities/` — domain UI and models (`tile`: tiles, hands, melds, discards; `table`: the game table model, the replay
  file reader and the board UI; `session`: the session machine; `client`: the dispatcher over client events, its
  state, timelines and seat scenarios, and the live board and rotate panel drawn from that state), imported through
  each slice's `index.ts`. A slice uses only slices below it: `client` may use `session` and `table`, `table` may use
  `tile`, never the reverse. Lint enforces the layering in `src`: `.oxlintrc.json` has one `no-restricted-imports`
  override per layer and slice, banning upward imports (the entry and the router included), any slice's internals but
  its own, and the tests. The tests are exempt from the slice and public-entry bans. A new slice needs its own
  override, or its self-imports fail. An override replaces the rule's options, so each one repeats the zod paths and
  the tests ban.
* `shared/` — protocol, handoff storage, the socket adapter, the replay fetch, the clock, config and small helpers;
  imports nothing above it. A helper two layers need goes to the lowest that may hold it: the wire's tile and seat
  arithmetic in `shared/protocol` (`tiles.ts`), a table rule (`ponOfType`) in the table slice.
* `fixtures/` — generated data (the seat transcripts and the replay files) and a loader that hands the transcripts
  over unparsed for the tests; it imports nothing, and only storybook views and tests import it.

## Conventions

* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Styles: Pico CSS v2 (`styles/_pico.scss`) styles semantic HTML; add classes only for project-specific components.
  The page is always dark (`index.html`), so `_pico.scss` assembles Pico's modules itself with only the dark scheme; a
  page using an element of a module it leaves out (a table, a dialog, a form control) enables that module there.
  Every colour is a `--ronin-*` token of `styles/_theme.scss`, the look spec's treatment A palette, never a literal in
  a component (a `color-mix` of tokens is fine); a new surface or mark takes an existing token or adds one there. The
  theme also sets Pico's own: its primary is the accent, so a plain button is the accent (the player's own action, the
  spec's one accent) and a `secondary` one the quiet outlined control.
* A tile's material is `styles/_tile.scss`'s alone: an ivory face with a rim (`--tile-ring`), an edge and a shadow
  (`--tile-lift`) cast toward the screen's bottom whatever the tile's turn (each turned frame sets `--frame-turn`, a
  sideways tile adds its quarter turn), all box shadows, so the material never moves a box; a back is the same box in
  one quiet colour, drawn by the stylesheet alone.
* Text has one face, `--ronin-font` (the face, Build), and no monospace: only the debug views (the `?debug` log, the
  storybook's sent messages) use `--ronin-font-debug`, which Pico's code elements take too. A figure that aligns (a
  score, a count, a timer, a result or standings figure) takes `type.figures` (`styles/_type.scss`) on its own numeric
  element, never on a container holding text: tabular digits, and `text-rendering: geometricprecision`, which stops
  headless Chromium snapping each digit's advance to a whole pixel. `styles/game-app.scss` is the one entry
  stylesheet; board layout lives in `styles/game-board/`.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.
* Lint and format follow the lobby's config (keep them in sync), but `new-cap`'s exceptions are this app's own: its
  capitalized lit-html components, each added as it is written. The `.oxlintrc.json` overrides relax only rules the
  code trips where it is shaped by its domain: the socket's replaceable `on*` handlers, the nested Zod tuples of the
  wire schemas and the long event dispatchers.
* Zod is `zod/mini` (lint bans classic Zod's specifiers in `src`, storybook views included: it does not tree-shake),
  with the English messages classic loads by default; the tests load `zod-setup.ts` too, so they read the app's
  messages. zod/mini's objects have no JIT, so `jitless` (`zod-setup.ts`) only guards against a classic schema
  slipping in, whose JIT's `new Function()` the game pages' CSP blocks. `zod-setup.ts` stays the first import of
  `index.ts`, ahead of any module that builds a schema.

## Tests

Vitest. UI tests render lit templates into a DOM element and assert on the result; logic tests call the module
directly. Tests live in `tests/`, outside `src/`, at the path of the module they cover
(`tests/entities/tile/hand.test.ts` for `src/entities/tile/hand.ts`), and import it through `@/`; a module whose tests
need different file-level `vi.mock`s gets a second, suffixed file. `tsconfig.json` includes `tests`, so
`npm run typecheck` checks them like `src`. Test helpers live in `tests/fixtures/` and are imported through the
`#tests/` subpath import (`package.json` `imports`), since a relative parent import fails lint. Build protocol events
with the event factories there, typed by the schemas' output, rather than as literals repeated across tests, so a
schema change fails the typecheck and is fixed in one place. Raw wire payloads for the dispatcher live there too, as
does the scenario stepper: session and dispatcher tests are written as sequences of client events with the effects
each step returns, never through the DOM, and a view's own tests inject fakes for its socket factory, loader and clock
rather than mocking modules. A seat scenario's payloads must parse, which its run checks.

The seat transcripts under `src/fixtures/seat-scenarios/` are generated too, never edited by hand (oxfmt skips them).
They sit in `src/` because the storybook renders them: the decisions stories run one to a labelled checkpoint
(`scenarioCheckpoint`, which the tests use too) and show the live board there, its controls stepping the dispatcher
with no socket. A lint rule bans importing `@/fixtures/*` from `src` outside the storybook views, so the transcripts
ship in the storybook's chunk alone, and the decisions storybook imports each transcript its stories run by name,
never the loader, so its chunk carries no other. `make generate-seat-scenarios` plays each scenario of
`backend/scripts/seat_scenarios/` through the real session manager, router and engine on virtual time, and the checks
fail when one drifts from what the server sends now. A new interaction case is a new scenario there, labelling the
messages and actions its tests look up. Every transcript runs through `runSeatScenario` with no mismatch, and the
tests assert named checkpoints apart from the effects (the open decision with its offers, wait id and deadline, the
table, the result), since matching effects alone passes with a wrong hand or decision. What the server cannot produce
is a hand-written branch on a generated scenario (`tests/fixtures/seat-transcripts.ts`): the client's own intents and
ticks (a kuikae or riichi discard it refuses, an expired prompt, a play switch turned on, `switchedOnBefore`), a
switch's send (the send the transcript recorded for the player's answer moved onto the message whose wait the switch
answers, the press after it then sending nothing, `answeredBySwitch`; written by hand with `expecting` where the
transcript recorded another answer), an answer racing a newer wait or the endpoint's rate limit (the harness skips the
endpoint, and a transcript keeps the server's order), and a payload edited to a shape the server never sends.

The replay files under `src/fixtures/replays/` are generated, never edited by hand (they sit in `src/` because the
replay storybook opens a few, each imported by name in a chunk loaded with its story): `make generate-replay-fixtures`
records each from a game the engine plays (`backend/scripts/replay_fixtures/`), and the checks fail when one drifts
from what the engine records now. A new replay case is a new scenario there. Tests load them through the fixtures'
loader, which reads them into the dispatcher's timeline as the replay view does, and the model's tests assert outcomes
on them, not only that they run: literals for what the model computes, and a field the model passes through compared
with the event it came from. Each is also projected per seat, as that seat's socket would receive it (another seat's
draw as its notice), to check that after every line the seat's view keeps every hand size, its own tiles, the wall and
the turn the replay shows.

The `describe` block names the subject (the module or function under test) and the `it` title says what it pins;
tests carry no doc comments, and source files carry no file-header comment.
