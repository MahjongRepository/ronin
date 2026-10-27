# Frontend

Two isolated apps, each its own Bun package with its own dependencies, lockfile, language, lint,
format and test config, and its own styles:

* `lobby/` — the scripts and styles of the server-rendered lobby pages (TypeScript / lit-html). See
  `lobby/AGENTS.md`.
* `game/` — the game client under `/play/*` (MajiangNG: JavaScript / jQuery). See `game/AGENTS.md`.

Neither app imports from the other, and nothing is shared between them at build time: a module both
need is copied into each. They meet only at the runtime contract
in `docs/architecture.md` (*Game client contract*), so the game client can be replaced by any app
that honours it.

## Tooling

Run a package's scripts from its directory (`cd frontend/game && bunx vitest run <path>`). The root
`make` targets (`install-frontend`, `lint-frontend`, `typecheck-frontend`, `format-frontend`,
`test-frontend`) loop over both apps.

Before Bun 1.4 (oven-sh/bun#35681), `bun remove` of a package another dependency lists as an
optional peer (e.g. `stylus` under Vite) leaves it in `bun.lock`: delete its `packages` line by
hand, then `rm -rf node_modules && bun install`, since `bun install` alone keeps its directories.

Both apps make every deprecation their own installed Sass marks active an error in our stylesheets,
by the same mechanism: the `lint` script's compile check (`--fatal-deprecation` with the installed
version) and Vite's dev and build (`fatalDeprecations` in `vite.config`). Dependencies' deprecations
(Pico's) stay warnings through quiet-deps. A Sass upgrade can therefore fail lint, the build and the
dev server on a newly deprecated construct; migrate it rather than silencing the deprecation.

`make run-local-server` runs one Vite dev server per app: the lobby's on `VITE_PORT` (5173), whose
scripts the lobby templates load directly, and the game client's on `GAME_VITE_PORT` (5174), which
the lobby proxies under `/game-assets/` so the game page stays on the lobby's origin. The game
client's HMR socket dials its Vite server directly (`server.hmr.clientPort`).

## UI changes

Vitest does not show what a page looks like, so a change to the UI is checked in the browser
(`.claude/skills/app-browser/SKILL.md` has the recipes):

* Capture every touched state, desktop through `agent-browser` and an iPhone in WebKit, both
  before (base commit) and after (working tree). "Touched" includes every state that shares the
  changed component or layout container (a lobby card restyle touches the room cards and the history
  cards; a board change touches the live game, the replay and the board storybook), not only the
  one the change targets.
* Take the before shots ahead of the first UI edit. Once the change exists, serve the base from a
  scratchpad `git worktree` with its own ports (`GAME_PORT`, `LOBBY_PORT`, `VITE_PORT`,
  `GAME_VITE_PORT` on `bin/run-local-server.sh`, after `make install-frontend` there). Its
  `backend/storage.db` starts empty, so register `dev` there too, in a separate
  `agent-browser --session` (the skill's *Logging in*). Stop it and `git worktree remove` it
  afterwards.
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
