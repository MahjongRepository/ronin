# Frontend

Two isolated apps, each its own npm package with its own dependencies, lockfile, language, lint,
format and test config, and its own styles:

* `lobby/` — the scripts and styles of the server-rendered lobby pages (TypeScript / lit-html). See
  `lobby/AGENTS.md`.
* `game_v2/` — the game client (TypeScript / lit-html). See `game_v2/AGENTS.md`.

No app imports from another, and nothing is shared between them at build time: a module two
need is copied into each. They meet only at the runtime contract
in `docs/architecture.md` (*Game client contract*), so the game client can be replaced by any app
that honours it.

## Tooling

Run a package's scripts from its directory (`cd frontend/game_v2 && npx vitest run <path>`). The root
`make install-frontend` and the frontend check targets run both apps.

Node is pinned to one exact version in two places, kept in step: the repo's `mise.toml` for
development (`mise trust && mise install` once; the `Makefile` puts that Node first on `PATH`) and
`NODE_VERSION` in `deploy/Dockerfile` for the image.

Each app's `.npmrc` holds the dependency policy: `save-exact` pins every version `npm install` adds,
and `min-release-age=7` makes npm resolve only versions published at least seven days ago, a
cooldown against a compromised release. Add or upgrade a package with `npm install <pkg>@latest`,
which takes the newest version past the cooldown; `make install-frontend` runs `npm ci` from the
lockfile. A package's install script runs only once `allowScripts` in `package.json` approves it
(`npm install-scripts ls`); every app denies `@parcel/watcher`'s, a node-gyp fallback build its
prebuilt binaries make unnecessary.

Each app's `.oxfmtrc.json` keeps `embeddedLanguageFormatting` off: with it on, oxfmt reflows the
HTML inside lit-html `html` templates, splitting tags as `</a\n>` to keep their whitespace exact.

Every deprecation the installed Sass marks active is fatal in each app's stylesheets, vendored Pico
included (`fatalDeprecations` in `vite.config.ts`; `lint` runs the same build in memory through
`scripts/check-build.ts`). A Sass upgrade can therefore fail lint, the build and the dev server on a
newly deprecated construct; migrate the construct rather than silencing the deprecation.

Each app owns its selected Pico 2.1.1 Sass modules and their dependencies in `src/assets/vendor/pico/`;
there is no Pico npm dependency. Edit these copies directly; they are maintained locally without
upstream syncing. Keep them independent, like the apps themselves. Sass entry points import them
through `@/assets/vendor/pico/`, using the app's existing `@/` alias for `src/`.
All local Sass `@use` and `@forward` paths and asset URLs use `@/`, including inside Pico;
Sass built-ins keep their `sass:` URLs.

Leave the vendored sources' formatting as it is (stylelint and the formatter ignore them). Keep each
copy's MIT `LICENSE.md` and its full notice in `legal/THIRD_PARTY_NOTICES.txt` in sync: `legal/` is
Vite's public directory, so that file is the notice the built app ships. See each copy's README for
provenance and maintenance.

Under `make run-local-server` the lobby templates load the lobby's scripts from its Vite server
directly, while the game client's is proxied under `/game-assets/v2/` so the game page stays on the
lobby's origin.

## UI changes

Vitest does not show what a page looks like, so a change to the UI is checked in the browser
(`.claude/skills/app-browser/SKILL.md` has the recipes):

* Capture every touched state, desktop through `agent-browser` and an iPhone in WebKit, both
  before (base commit) and after (working tree). "Touched" includes every state that shares the
  changed component or layout container (a lobby card restyle touches the room cards and the history
  cards; a board change touches the live game, the replay and the board storybook), not only the
  one the change targets.
* The v2 client is the exception: its before and after are only the changed area plus its one worst
  case, shot by its targeted visual check (the skill's *Targeted v2 screenshots*;
  `frontend/game_v2/AGENTS.md`, Visual check).
* Take the before shots ahead of the first UI edit. Once the change exists, serve the base from a
  scratchpad `git worktree` with its own ports (`GAME_PORT`, `LOBBY_PORT`, `VITE_PORT`,
  `GAME_V2_VITE_PORT` on `bin/run-local-server.sh`, after `make install-frontend` there). Its
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
