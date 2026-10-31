# Game client (MajiangNG: JavaScript / jQuery)

The default game client under `/play/*`: a fork of kobalab's 電脳麻将 (MIT, `LICENSE`). majiang-ui components draw a
majiang-core model; `src/js/ronin/` speaks ronin's protocol and drives that model. Out of `make run-all-checks`
(`frontend/AGENTS.md`): run its lint and tests by hand when you touch it.

## Structure

* `src/vendor/majiang-core/` and `src/vendor/majiang-ui/` are our forks, edited in place; keep each MIT `LICENSE`.
  They are ES modules imported by relative path: Vite does not serve CommonJS outside `node_modules`.
* `majiang.js` sets the globals `Majiang` and `$`/`jQuery` and stays the first import of `main.js`.
* `index.html` holds the board markup majiang-ui binds to by class name and `#loaddata` (tile images and sounds the UI
  clones); a route that draws tiles keeps `#loaddata`. The replay's error screen (`showProblem`) copies the loading
  screen's layout: change both together.
* Static assets in `public/` are referenced by absolute path (`/img/…`); a relative path skips the Vite base.
* `src/js/ronin/` never imports `src/js/replay/`. The replay reuses the live client's pure builders (`results.js`),
  never the live shadow.
* A new route also needs its path in the lobby's game page list (`backend/lobby/server/app.py`).

## Protocol rules

* **The server judges every decision.** majiang-core's own rule checks never decide a button or a selectable tile;
  `player.js` offers exactly what the server offered (the server disconnects a seat for an impossible action). The one
  rule the client applies is which tile may be discarded (any; in riichi only the drawn one).
* The turn after the seat's own pon or chi opens on the server's `turn` event, never on the meld. A reconnect
  snapshot opens no decision: the server re-sends the wait.
* Every action echoes the wait id of the last server message that carried one, never a game error's.
* A left click on the felt answers nothing, so a stray click never passes a ron or dismisses a result.
* Auto switches answer through the click path, only decisions opened after they are turned on, never a refused
  answer's retry.
* Credentials come only from the lobby's handoff or its recovery endpoint, never the URL.
* A countdown that runs out sends nothing, never majiang-ui's default reply: the server's timeout acts.
* Closes 4002 and 1008 are permanent and cancel any retry; every other close reconnects.
* `src/js/ronin/wire.js` mirrors the backend's wire enums and replay format: change both together.
* The silence watchdog's limit (`RoninSession`) is hand-derived from the backend's session `TimerConfig`
  defaults; re-derive it when pacing changes.
* No logic reads displayed text: draws carry a stable `code`, yaku the server's id.

## Language

Contract and glossary in `docs/i18n.md`; catalogs in `src/i18n/locales/`. Code holds no literal UI text, and a
translated string never goes through jQuery `.append(string)`/`.html()` (`tNodes()` for a sentence with an element).
A locale switch in the live game never rebuilds hand, river, meld or button nodes, so the open decision and focus
survive.

## Conventions

* Upstream-style code (`src/vendor/`, `majiang.js`, `ronin.js`, `src/js/ronin/`, `index.html`) keeps its own style:
  oxfmt ignores it and oxlint relaxes rules it trips. Ronin code is formatted and fully linted.
* SCSS partials load with `@use`; colours and fonts from `styles/_theme.scss`; divide with `math.div`. Class names
  are kebab-case; one the JS or `index.html` sets is renamed there too.
* Tests: Vitest with happy-dom in `src/js/__tests__/`. `describe` names the subject, `it` says what it pins. The
  replay fixtures there are a frozen copy no make target regenerates.
