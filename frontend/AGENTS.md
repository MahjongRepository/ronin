# Frontend (TypeScript / lit-html)

Two apps from one source tree, built by Vite with Bun: the lobby scripts that enhance the
server-rendered lobby pages, and the game client SPA. `src/shared/protocol/` and
`src/entities/table/` have their own `AGENTS.md`.

## Tooling

The `package.json` scripts are the reference, run from `frontend/` or through the root `make`
targets. Two things they don't show:

* `bun run sprite` rebuilds the tile sprite from the tile SVGs after one changes; the sprite is
  committed. `entities/tile/lib/tile-config.ts` is the single source for the active tile set.
* Vite builds two entries, game and lobby, served under `/game-assets/`; the lobby backend maps them
  into its templates from the Vite manifest, or from the Vite dev server under
  `make run-local-server` (`backend/lobby/AGENTS.md`).

## Apps

* **Lobby** (`src/lobby/`): no routing; the Jinja2 templates in `backend/lobby/views/templates/` are
  the pages, and `lobby/index.ts` loads on all of them and starts whatever the page holds (the room,
  the matchmaking queue, the history copy-link buttons). `lobby-socket.ts` is the JSON lobby
  WebSocket; it neither reconnects nor watches for a silent server.
* **Game client** (`src/index.ts` → `router.ts` → `views/`): pathname routes for the live game, the
  replay (loaded over HTTP) and the storybook component showcase. Each route may register a cleanup
  the router runs on navigation.
* **Handoff:** the lobby script stores the game socket URL and ticket per game (`shared/session/`)
  and navigates to the game client, which joins with the ticket and, after a disconnect, reconnects
  with backoff and resumes the seat with the same ticket. A "retry later" reconnect error is
  retried; every other reconnect error sends the player back to the lobby.
* **Silence watchdog:** the client sends nothing on its own, so a socket whose peer vanished never
  fires `onclose`. `GameSocket` therefore treats a server silent longer than any legitimate wait as
  a disconnect, measured on the wall clock so the first check after a device wake sees the whole
  gap. The limit is hand-derived from the session `TimerConfig` defaults
  (`backend/game/session/AGENTS.md`, Pacing) plus a margin for late timers; re-derive it when the
  pacing changes.

## Structure

Imports use the `@/` alias for `src/`. Layers depend downward only, and follow the existing tree
rather than introducing new FSD layers:

* `views/` and `lobby/` — route views and lobby page scripts; they compose entities and shared code
  and never import each other.
* `entities/` — domain UI and models (`tile`: tiles, hands, melds, discards and the tile-id
  helpers; `table`: the game table model and board UI), imported through each slice's `index.ts`;
  `table` may use `tile`, never the reverse.
* `shared/` — protocol, session, WebSocket and config; imports nothing above it.

## Conventions

* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Lobby page modules split like `lobby/room/`: `state.ts` (state and pure queries), `handlers.ts`
  (everything that reads or writes the socket, taking the state first), `ui.ts` (templates only,
  never the socket), `index.ts` (wiring). The server is authoritative: derive ready state, owner and
  start permission from its messages, don't keep a local copy.
* Styles: Pico CSS v2 (`styles/_pico.scss`) styles semantic HTML; add classes only for
  project-specific components. Use the `--ronin-*` tokens from `styles/_theme.scss` rather than
  literal colors and fonts. Each app has one entry stylesheet (`lobby-app.scss`, `game-app.scss`);
  board layout lives in `styles/game-board/`.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.
* Zod runs jitless (`zod-setup.ts`): its JIT uses `new Function()`, which the game pages' CSP
  blocks. `zod-setup.ts` stays the first import of `index.ts`, ahead of any module that builds a
  schema.

## UI changes

Vitest does not show what a page looks like, so a change to the UI is checked in the browser
(`.claude/skills/app-browser/SKILL.md` has the recipes):

* Capture every touched state, desktop through `agent-browser` and an iPhone in WebKit, both
  before (base commit) and after (working tree). "Touched" includes every state that shares the
  changed component or layout container (a lobby card restyle touches the room cards and the history
  cards; a board change touches the live game, the replay and the board storybook), not only the
  one the change targets.
* Take the before shots ahead of the first UI edit. Once the change exists, serve the base from a
  scratchpad `git worktree` with its own ports (`GAME_PORT`, `LOBBY_PORT`, `VITE_PORT` on
  `bin/run-local-server.sh`, with `frontend/node_modules` symlinked in). Its `backend/storage.db`
  starts empty, so register `dev` there too, in a separate `agent-browser --session` (the skill's
  *Logging in*). Stop it and `git worktree remove` it afterwards.
* Save them to `thoughts/screenshots/<topic>/`, named so each pair sorts together:
  `1-desktop-lobby-a-before.png`, `1-desktop-lobby-b-after.png`, `2-phone-lobby-a-before.png`.
* Read every after shot next to its before, the way a player will see it: a consistent grid and
  alignment, even spacing, a clear hierarchy (one primary action), no wrapped or overflowing text,
  nothing clipped off the viewport, no stray empty areas, nothing lost or duplicated versus before.
  No glitches is not the same as a good layout; fix what reads poorly and re-shoot.
* Each pair shows the same data and state. Anything the diff does not explain is a bug or a broken
  capture until a re-shoot proves otherwise; never report it as a capture artefact or an acceptable
  fallback. Fix it, or ask.
* Then list the files for the user with a one-line verdict per pair.

## Tests

Vitest. UI tests render lit templates into a DOM element and assert on the result; logic tests call
the module directly. New tests go in a `__tests__/` directory beside the code. The `describe` block
names the subject (the module or function under test) and the `it` title says what it pins; tests
carry no doc comments, and source files carry no file-header comment.
