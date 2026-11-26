# Frontend

No app imports from another; a module both need lives in `shared/`, and each app bundles its own
copy of what it imports. At runtime they still meet only at the contract in `docs/architecture.md`
(*Game client contract*), so the game client can be replaced by any app that honours it. Pico copies
and styles stay per app.

Both apps draw corners with the same two radii, each from its own `_theme.scss`: `--ronin-corner-label`
for a small label, badge, chip or key hint, `--ronin-corner-panel` for a panel, card, menu or control.
Only round shapes (dots, seats, the riichi stick), the tiles and the result's seal draw their own;
nothing else picks a radius.

## Tooling

Node is pinned to one exact version in two places, kept in step: the repo's `mise.toml` for
development (`mise trust && mise install` once) and
`NODE_VERSION` in `deploy/Dockerfile` for the image.

Each app's `.npmrc` holds the dependency policy (exact pins, a seven-day release cooldown). Add or
upgrade a package with `npm install <pkg>@latest`, which takes the newest version past the cooldown.
A package's install script runs only once `allowScripts` in `package.json` approves it
(`npm install-scripts ls`); `@parcel/watcher`'s stays denied because its prebuilt binaries make the
node-gyp fallback build unnecessary.

Each app's `.oxfmtrc.json` keeps `embeddedLanguageFormatting` off: with it on, oxfmt reflows the
HTML inside lit-html `html` templates, splitting tags as `</a\n>` to keep their whitespace exact.

Every deprecation the installed Sass marks active is fatal in each app's stylesheets, vendored Pico
included (`fatalDeprecations` in `vite.config.ts`; `lint` runs the same build in memory through
`scripts/check-build.ts`). A Sass upgrade can therefore fail lint, the build and the dev server on a
newly deprecated construct; migrate the construct rather than silencing the deprecation.

Each app's Pico 2.1.1 subset lives in `src/assets/vendor/pico/` (provenance and maintenance in its
README): edit it directly and never sync it from upstream. All local Sass `@use` and `@forward` paths
and asset URLs use `@/`, inside Pico too; Sass built-ins keep their `sass:` URLs.

Leave the vendored sources' formatting as it is. Keep each copy's MIT `LICENSE.md` and its full notice
in `legal/THIRD_PARTY_NOTICES.txt` in sync: `legal/` is Vite's public directory, so that file is the
notice the built app ships.

Under `make run-local-server` the lobby templates load the lobby's scripts from its Vite server
directly, while the game client's is proxied under `/game-assets/v2/` so the game page stays on the
lobby's origin.

## UI changes

Vitest does not show what a page looks like, so a change to the UI is checked in the browser
(`.claude/skills/app-browser/SKILL.md` has the recipes):

* Shoot only the changed area plus its single worst case (the densest state that holds the changed
  element, the smallest phone), desktop through `agent-browser` and an iPhone in WebKit, both before
  (base commit) and after (working tree). The v2 client shoots them with its targeted visual check
  (the skill's *Targeted v2 screenshots*; `frontend/game_v2/AGENTS.md`, Visual check).
* Take the before shots ahead of the first UI edit. Once the change exists, serve the base from a
  scratchpad `git worktree` with its own ports (`GAME_PORT`, `LOBBY_PORT`, `VITE_PORT`,
  `GAME_V2_VITE_PORT` on `bin/run-local-server.sh`, after `make install-frontend` there). Its
  `var/storage.db` starts empty, so register `dev` there too, in a separate
  `agent-browser --session` (the skill's *Logging in*). Stop it and `git worktree remove` it
  afterwards.
* Save them to `thoughts/screenshots/<topic>/`, as many as the work needs. What the human reviews is
  `<topic>/_final/`: the latest before/after collages only, one per screen class (`mobile.png`,
  `laptop.png`, `desktop.png`), built as the skill's *Final screenshots* says.
* Read every after shot next to its before, the way a player will see it: a consistent grid and
  alignment, even spacing, a clear hierarchy (one primary action), no wrapped or overflowing text,
  nothing clipped off the viewport, no stray empty areas, nothing lost or duplicated versus before.
  No glitches is not the same as a good layout; fix what reads poorly and re-shoot.
* Each pair shows the same data and state. Anything the diff does not explain is a bug or a broken
  capture until a re-shoot proves otherwise; never report it as a capture artefact or an acceptable
  fallback. Fix it, or ask.
* Then list the `_final/` files for the user with a one-line verdict each.
