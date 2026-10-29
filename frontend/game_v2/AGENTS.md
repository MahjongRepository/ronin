# Game client v2 (TypeScript / lit-html)

The earlier game client SPA, restored as the foundation of a future client: the lobby serves it
instead of `frontend/game/` on any game page whose query has `v=2` (`/play/{game_id}?v=2`,
`/play/history/{game_id}?v=2`). Its protocol layer parses the current protocol and replay format,
but the views act on less of it than v1 does: the live game plays its decisions on the board (the
discard, the offers, pass, the countdown and furiten) and the round results the player confirms, while
player names on the board are not there yet.
Adapt the client to the server rather than the server to it. `src/shared/protocol/` and
`src/entities/table/` have their own `AGENTS.md`.

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
  live game is the entry chunk; the replay and the storybook are lazy routes (`lazyRoute`), each a
  chunk of its own that brings its own stylesheet (`styles/replay-page.scss`,
  `styles/storybook-page.scss`), so neither ships to a player who only plays. The lobby lists each
  game page path with its login policy (`backend/lobby/server/app.py`) and 404s any other, so a new
  route needs its path added there.
* **Views are controller instances, one per mount.** A view is given its host, its sources and
  sinks (the socket factory, the replay loader, the handoff, its lookup and the navigation) and its clock;
  `index.ts` is the one place that wires the browser's. A view keeps no module state, looks up no
  element by id and renders one top-level template into its host. Its input is its own: keys reach
  it only through its own focusable root, and a click outside closes only its own dropdown, so two
  mounts never move together. Its dispose cancels every timer, socket, fetch and listener it owns
  and clears its host, and a callback that still fires afterwards is dropped. The game view's
  driver ends the client as failed, on the page, when a step or an effect throws, rather than
  leaving its queue stuck, and reports a socket factory that throws as a failed connection.
* **One dispatcher over client events.** The live game, the replay and scripted scenarios all run
  on `entities/client`'s dispatcher, a pure `(state, event) → { state, effects }` over an explicit
  client event union (`ClientEvent`): server messages arrive as raw wire payloads and replay lines
  as raw JSON objects, both parsed inside, beside the transport's events, logical time ticks and
  local user intents. Every event carries the logical time its source stamped, and the state keeps
  the last one as its `now`, so a state kept at a historical cursor keeps its time. The transitions
  never run IO, read a clock or start a timer: they return descriptions of real IO only
  (`ClientEffect`), and only the live driver (`views/game.ts`) executes them. Timers are not
  effects: the state holds its pending deadlines, `nextDeadline` derives the earliest, and the
  driver keeps one timer armed to it that comes back as a tick. A tick before a deadline, or with
  none, does nothing, so a stale timer cannot act. Display-only data (the game view's debug log)
  stays in the view, out of the state.
* **One client state.** The dispatcher composes the session, the table (`entities/table`) and the
  viewer's interaction into one immutable state: the viewer's seat, its open decision, its
  furiten, the timer settings and the round confirm it owes. A replay is the same state with no
  session and no viewer; visibility (a replay's every hand, a live seat's own) is what the source
  showed and how the board is drawn, never a second model, and the seat at the bottom is the
  view's choice (the replay's is the recorded first dealer's, `docs/architecture.md`, Replays).
* **Decisions.** A decision opens only from a message carrying a wait id to the viewer's seat (its
  draw, its `turn` event, its call prompt), with the offers the server listed and nothing the
  client judged but the discard rule (kuikae, riichi's drawn tile). Its deadline is the client's
  estimate of the server's timer, in logical time from the timer settings and the bank the opening
  message names (none when it names no bank), backdated by a re-sent wait's elapsed time, so a
  countdown reads from `now`, never the wall clock. Past it the decision shows as expired, for
  display only: the server alone decides by the wait id whether an answer counts, so an expired
  decision still takes one answer, and the client never answers on its own. Answering sends the
  action with the decision's wait id once and marks it submitted; the server's next move closes
  it, a refusal while its wait goes on (a game error but a stale one, or the socket's rate limit)
  reopens it, and a dropped socket drops it, since the reconnect re-sends a wait the server still
  owes the seat.
* **Round confirm.** A round end's wait, or a reconnect's snapshot of a round advance that says the
  seat still owes it, opens the round confirm like a decision: one confirm intent sends it once with
  that wait id, then the seat waits for the others. Only the next deal (the last confirm's or the
  timeout's) closes it, and only the socket's rate limit reopens a sent one; a game error never
  touches it, since a late reply to an earlier move names no wait and the confirm's own stale reply
  follows the deal that closed it. A dropped socket drops it, since the snapshot says again whether
  it is owed. Its deadline is one per round, armed at the round end: the round advance timeout times
  the result's pages (the server's `results_shown`, a double ron's winners), backdated by the
  snapshot's elapsed time, and none when the snapshot names none: never a fresh full timeout. It is
  display only, shown labelled and kept while the seat waits: the client never confirms on its own
  and arms no timer for it. A double ron's pages each show Next until the last, which alone
  confirms, so the player has seen every winner before confirming. The game's last round end
  carries no wait and its game end follows at once: the table keeps that result and the live board
  shows it over the standings until the player dismisses it, which sends nothing.
* **Timelines, not history in the driver.** `buildClientTimeline` steps any event sequence into
  the state after each event; stepping back selects an earlier state, never an inverse event, and
  nothing in a timeline executes an effect, so revisiting a prompt sends nothing and arms no
  timer. The replay view reads its file into such a timeline, and each of its stops is one of the
  timeline's states. The dispatcher takes one event in one step, except a replay's round end that
  robbed a kan, which the replay records no declaration line for: it takes that in two steps, the
  kan declared and then the result, each an entry of the timeline (`stepGameClient` returns both
  as one). A live game's own history review, if ever wanted, keeps the authoritative state moving
  forward apart from its cursor.
* **Scenarios.** A `SeatScenario` (`entities/client`) is one seat's scripted run as plain data:
  the lobby handoff, then ordered client events, each step naming exactly the effects it must
  describe (none when omitted), so every send is asserted and never fed in. `runSeatScenario`
  builds its timeline and reports every step whose effects part from the scenario, a payload that
  does not parse included. `seatScenarioFromTranscript` builds one from a seat transcript the
  backend generated (what the server sent one seat and what the seat sent it, JOIN_GAME and
  RECONNECT included with the ticket left out, and the closes it saw, parsed strictly with Zod where
  it arrives as JSON). It drives the client as the live driver does, ticking at each deadline the
  client holds before the next recorded event, but takes the effects it expects only from the
  transcript and the contract, never from the client logic under test: each recorded send at its
  recorded time (an answer or a round confirm as the intent choosing it, a send the client makes on
  its own, a resent identity, as a tick then, the identity after an open as that open's effect), a
  reopened socket asked for at its recorded open, the handoff forgotten after a close the contract
  makes terminal (its own copy of the codes), and nothing from any other tick, so an automatic send that is
  early, late or missing is a mismatch. Because sent messages parse strictly, an expected send also
  pins the builders' wire shape to what the server accepted. The tests run the generated ones;
  nothing in the app runs one yet.
* **Components take faces, mappers take ids.** `Hand`, `Discards` and `Meld` take display tiles
  keyed by `TileFace` (a meld as the tiles `meldTiles` lays it out), never raw tile ids; the mappers
  convert. A hand tile keeps its tile id when it came from a table, and one of the viewer's own may
  be playable: selectable, selected, disabled or waiting. Every playable tile is a native button
  (focus, Enter and Space, a visible focus ring, a named action) whatever its state, so a turn never
  moves focus out of the hand; only a selectable one acts, the others carry `aria-disabled` (the
  selected one, the tile an answer played, `aria-pressed` too). The hand reports a pressed
  selectable tile's id and nothing else. Orientation stays with the
  board's strips, which rotate whole hands.
* **The board renders a display state; a mapper derives it.** `GameBoard` (`entities/table`) renders
  a `BoardDisplayState` with slots for an overlay, the local hand's input and a corner for the
  decision's controls, and decides nothing. `tableStateToDisplayState` maps a table from a
  perspective; `playDisplay` (`entities/client`) maps a whole client state for the live board: the
  table from the viewer's seat with only its hand face up, each of its tiles marked by the open
  decision, the intent each selectable tile sends, the decision's buttons (riichi as one toggle,
  then each other offer, then a pass), the countdown and furiten, and the round result's controls
  (its one primary button, the result's pager only secondary beside it, the countdown, waiting for
  the others). What may be played is never
  restated there: every tile intent and button is one the dispatcher's own `takesIntent` takes (the
  decision's answer on a socket it can send on), so the board offers exactly what stepping the
  intent would send. `PlayBoard` only renders that, with the table's panel over it, and routes a
  command: an intent goes to the dispatcher; the view state is `PlayUi`, an input of the mapper too:
  the riichi toggle, keyed by the decision's wait id so a newer decision never inherits it, and the
  round result's page, keyed by the round the result ends (its wind, dealer and honba, which a
  reconnect's snapshot names alike), so a newer result opens on its first page while a reconnect
  keeps the page. A new prop on the board is added to these mappers when a scenario shows the need,
  never computed in a view.
* **Session** (`entities/session`): one machine owns finding the handoff, joining, playing,
  reconnecting and the end. It joins with the lobby's ticket (`shared/session` holds the handoff) and
  resumes the seat with the same ticket. A tab that holds no ticket asks the lobby
  (`GET /api/game-session`) through an effect the driver runs and cancels on dispose: this game's
  handoff is kept and joined with, another game's kept and its page opened (the query, so `?v=2`,
  carried over), none sends the player to the lobby, and a failed lookup is asked once more after a
  short wait (`policy.ts`), then stays on the page with a reload. Two retries stay distinct, each with its own backoff and budget: a transport
  retry reopens a dropped socket, a session retry resends RECONNECT on the open socket after
  `reconnect_retry_later` (honoured only while reconnecting) or a rate limit on its JOIN_GAME or
  RECONNECT (only before the seat is held). A drop supersedes a waiting session retry, since the
  reopened socket sends RECONNECT itself. A socket that has not opened by its connect deadline (a
  state deadline like the others) is closed and retried as a drop. The stop policy follows the
  server: the 4002 and 1008 closes, a refusal that means the ticket will never hold the seat again,
  and a spent retry budget end the session, cancel its retry and forget the handoff, and stay on the
  page, whose board says why with a way back; a game end ends it on the page; any other close is
  retried, 1000 included (`docs/architecture.md`, Game client contract). An ended session ignores
  everything after, except that leaving still goes to the lobby from an end that stayed on the page.
  Leaving while the session holds or works for the seat hands it to an AI, so the page asks first
  (`PlayUi`), modally: the rest of the page is inert, Stay is the primary action and takes the focus,
  Escape stays, and staying returns the focus to the control that asked; after an end it leaves at
  once.
* **Silence watchdog:** the client sends nothing on its own, so a socket whose peer vanished never
  fires `onclose` (one that never opens is the session's connect deadline instead). `GameSocket`, the socket's thin IO adapter (one connection attempt per
  instance; it never reconnects), therefore reports a server silent longer than any legitimate
  wait as a close, measured on the wall clock so the first check after a device wake sees the whole
  gap. The limit is hand-derived from the session `TimerConfig` defaults
  (`backend/game/session/AGENTS.md`, Pacing) plus a margin for late timers; re-derive it when the
  pacing changes.

## Layout

* **Browser floor: iOS Safari 16.4** (range media syntax; container queries need 16.0, `dvh` 15.4),
  and the smallest supported landscape is 667x375 (iPhone SE 2nd and 3rd generation): the 568x320
  phones never got iOS 16.4, so they are below the floor.
* **The live game's page** is the board beside an aside holding the way back and the session's
  status in a player's terms, as the rotate panel words it. The board carries the notices
  (`playDisplay`'s, in the table's own area so they never cover the hand or the decision's corner): a
  seat this page held and lost to a drop while it reconnects, or a connection failing since the page
  opened, each worded the same across its retries so it is announced once (a page that only resumes
  its seat, a reload, shows neither); short-lived ones held in the client state with a logical-time
  expiry (the seat back after a snapshot of such a drop, which a second drop replaces, and a refused
  move); and a server message the client cannot read, on the console too, shown until a reconnect's
  snapshot rebuilds the table, which may be wrong until then. An end that stops the session on the
  page blocks the board, and takes the rotate panel's place, with why and a way back. With `?debug` (any value but `0`, `false`, `no` or `off`) the aside adds the debug log, a
  collapsed sheet of every message, send and transport event under the machine's own status; without
  it the view keeps no log at all.
* **Phone policy: the live game is played in landscape.** On an upright touch screen narrower than
  600px (`(orientation: portrait) and (width < 600px) and (pointer: coarse)`, so a narrow desktop
  window is never told to rotate a phone), the game view shows the rotate panel (`entities/client`) in
  place of its play area. A media query alone chooses it: no Screen Orientation lock, which iOS Safari
  lacks. Both are rendered from the same state, so the socket, the session and its timers run on
  underneath. The panel shows the session's status in a player's terms, a way back to the lobby and,
  while a decision or a round result's confirm awaits the viewer, that play and its countdown go on,
  with the seconds left. Only the status line and the countdown's thresholds (10 s, 5 s, expiry) are
  live regions, never each second. The server's timer never pauses for it, so a decision left unrotated can time out: an
  accepted cost. The countdown reads the deadline against the state's `now`, never the wall
  clock; the driver also wakes at each change of the shown second (`nextCountdownChange`) so `now`
  moves. Replay and storybook pages take no timed input: they allow portrait and scroll rather than
  clip.
* **The board sizes itself from its own box.** `.game-board` is a size container and every length in it
  derives from its width and height (container query units), never the viewport or a fixed tile size.
  The local strip (the bottom seat's hand, its melds smaller) spans the bottom edge and takes its share
  of the height first; the dora take a corner of their own, beside the table on a wide board and above
  it otherwise; the table fits what is left in both directions. Each other seat has one strip along its
  edge, its melds sharing the hand's track, so a hand shrinks as its melds grow and the two never
  overlap. Inside the table, lengths are counted in board units (a tile is 60 x 80); the Sass constants
  in `game-board/_grid.scss` give every track in those units and the spans the unit is fitted to, and
  `--board-unit` is the length of one unit, the smaller of the table's width and height over those
  spans. The local strip, the dora and the overlay set their own unit the same way. Breakpoints, as
  container queries, change density only. Text the board scales keeps a 10px floor. The decision's
  corner is the board's own grid area, beside the table opposite the dora on a wide board (its
  buttons wrapping down toward the hand, for the thumb) and beside the dora above the table
  otherwise (one row that scrolls sideways); it is sized by its area, never its content, so offers
  scroll inside it rather than squeeze the table.
* **Pages never clip the board.** `.board-page` gives it a definite box, sized with `dvh` and the
  safe-area insets (the theme's `--ronin-safe-*`, which a test can set), and puts its aside (controls,
  story switches) below it upright, or beside it in landscape as a compact column that scrolls when the
  window is too short for it.
* **Visual gate:** `make visual-check` builds the app, checks the bundle budget, serves `dist/`
  with a replay fixture and a seat transcript over a mocked socket (no backend), and loads every
  storybook page (the board's worst case among them: every seat with four melds, long rivers, five
  dora, AI marks; the dense round results; and the decisions stories), the replay and the live game, at its call prompt and at
  its turn, at 1280x800 (Chromium),
  iPhone 13 portrait, iPhone 13 landscape with a notch's insets and the 667x375 floor (WebKit). The
  two engines run at once and each checks several pages at a time, each in its own context. It
  fails on content that is hidden or empty, tiles of different areas overlapping, anything outside
  the board or the screen, page overflow, centre text under 10px, local hand tiles under 32x42 or
  decision buttons under 40x40 in landscape, a round end that does not fit its panel, an aside that
  hides its controls, a rotate panel missing on an upright phone or shown elsewhere, and any console
  error, failed request or missing element. It writes a screenshot per page to
  `thoughts/screenshots/visual-check/`. `make install-frontend` installs its Chromium and WebKit
  (`npx playwright install`, matching the pinned `playwright`); on a fresh Linux host their system
  libraries come from `npx playwright install-deps`, which needs root. A board state worth checking
  at phone size is a storybook state and a case there; one the generated scenarios reach is a
  decisions story rather than a hand-written one. On success `make visual-check` stamps a
  fingerprint of its inputs (every non-ignored file under `frontend/game_v2`, tracked or not, and the
  `Makefile`) in `node_modules/.cache/visual-check.pass`; `make run-all-checks` skips the gate only
  when the current fingerprint matches that stamp, so a skip always means these exact inputs passed.
  Run directly, it always runs.
* **Budgets**, in the same run: `scripts/bundle-budget.ts` reads the manifest the gate's build alone
  writes (`vite build --manifest`; it deletes it, so `dist/` never serves one) and fails when a
  route loads more JavaScript or CSS than its budget, raw or gzipped (the game route is the entry
  and its static imports; a lazy route is what it adds), the budgets set about a tenth over the
  measured sizes, a lazy route's CSS at least 1 KiB over. Then the replay load budget loads the
  largest engine replay fixture on the same server and Chromium, slowed sixfold
  (`Emulation.setCPUThrottlingRate`), and fails when the median of a few reads of the replay view's
  `replay-load` measure (parse, reduce into the client timeline, steps and navigation index, before
  the first render) exceeds its budget. A run counts only when its measure's detail shows it read
  the whole fixture (its steps, rounds, final standings and no unreadable line) in a finite time.
  The timing depends on the host's CPU, so the budget is set well above this host's median. Growing
  past a budget is a decision made in the script with the new measurement, not a drift.

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree
rather than introducing new FSD layers:

* `views/` — route views; they compose entities and shared code.
* `entities/` — domain UI and models (`tile`: tiles, hands, melds, discards and the tile-id helpers;
  `table`: the game table model, the replay file reader and the board UI; `session`: the session
  machine; `client`: the dispatcher over client events, its state, timelines and seat scenarios, and the
  live board and rotate panel drawn from that state),
  imported through each slice's `index.ts`. A slice uses only slices below it: `client` may use
  `session` and `table`, `table` may use `tile`, never the reverse.
* `shared/` — protocol, handoff storage, the socket adapter, the replay fetch, the clock, config and
  small helpers; imports nothing above it.
* `fixtures/` — generated data (the seat transcripts) and a loader that hands all of it over
  unparsed for the tests; it imports nothing, and only storybook views and tests import it.

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
`tsconfig.json` includes `tests`, so `npm run typecheck` checks them like `src`. Test helpers live
in `tests/fixtures/` and are imported through the `#tests/` subpath import (`package.json`
`imports`), since a relative parent import fails lint. Build protocol events with the event
factories there, typed by the schemas' output, rather than as literals repeated across tests, so a
schema change fails the typecheck and is fixed in one place. Raw wire payloads for the dispatcher
live there too, as does the scenario stepper: session and dispatcher tests are written as
sequences of client events with the effects each step returns, never through the DOM, and a view's
own tests inject fakes for its socket factory, loader and clock rather than mocking modules. A seat
scenario's payloads must parse, which its run checks.

The seat transcripts under `src/fixtures/seat-scenarios/` are generated too, never edited by hand
(oxfmt skips them). They sit in `src/` because the storybook renders them: the decisions stories run
one to a labelled checkpoint (`scenarioCheckpoint`, which the tests use too) and show the live board
there, its controls stepping the dispatcher with no socket. A lint rule bans importing
`@/fixtures/*` from `src` outside the storybook views, so the transcripts ship in the storybook's
chunk alone, and the decisions storybook imports each transcript its stories run by name, never
the loader, so its chunk carries no other. `make generate-seat-scenarios` plays each scenario of
`backend/scripts/seat_scenarios/` through the real session manager, router and engine on virtual
time, and the checks fail when one drifts from what the server sends now. A new interaction case
is a new scenario there, labelling the messages and actions its tests look up. Every transcript
runs through `runSeatScenario` with no mismatch, and the tests assert named checkpoints apart from
the effects (the open decision with its offers, wait id and deadline, the table, the result), since
matching effects alone passes with a wrong hand or decision. What the server cannot produce is a
hand-written branch on a generated scenario: the client's own intents and ticks (a kuikae or
riichi discard it refuses, an expired prompt), an answer racing a newer wait or the endpoint's rate
limit (the harness skips the endpoint, and a transcript keeps the server's order), and a payload
edited to a shape the server never sends.

The replay files under `tests/fixtures/replays/` are generated, never edited by hand:
`make generate-replay-fixtures` records each from a game the engine plays
(`backend/scripts/replay_fixtures/`), and the checks fail when one drifts from what the engine
records now. A new replay case is a new scenario there. Tests load them through the fixtures'
loader, which reads them into the dispatcher's timeline as the replay view does, and the model's
tests assert outcomes on them, not only that they run: literals for what the model computes, and a
field the model passes through compared with the event it came from. Each is also projected per
seat, as that seat's socket would receive it, to check that a seat's view keeps every hand size,
its own tiles, the wall and the turn the replay shows.

The `describe` block names the subject (the module or function under test) and the `it` title says
what it pins; tests carry no doc comments, and source files carry no file-header comment.
