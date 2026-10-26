# Game client (MajiangNG: JavaScript / jQuery)

The game client under `/play/*`: a fork of kobalab's 電脳麻将 (MajiangNG, MIT, see `LICENSE`). Its UI
is the majiang-ui components drawing a majiang-core model; `src/js/ronin/` is the layer that speaks
ronin's game protocol and drives that model. Plain JavaScript ES modules, built by Vite with Bun.

## Vendored libraries

* `src/vendor/` holds our forks of kobalab's libraries, no longer npm dependencies:
  `majiang-core/` from `@kobalab/majiang-core` 1.4.1 and `majiang-ui/` from `@kobalab/majiang-ui`
  1.6.1. The commit that added them is the published `lib/` verbatim, so `git diff` against it shows
  everything we changed. Edits there are ours; each directory's MIT `LICENSE` stays.
* The fork is ES modules, imported by relative path (majiang-ui imports `../majiang-core/index.js`):
  Vite neither dev-serves nor builds CommonJS outside `node_modules`.
* majiang-ui is pruned to what the live game and the storybook draw: its paipu viewer, file manager,
  editor, analyzer and stats are gone, and with them majiang-ai, jquery-ui and tenhou-url-log. Its
  only remaining dependency is `jquery`.

## Build

* `index.html` is the one page for every route. It is upstream's `ronin.pug` rendered once, and it
  holds the board markup the majiang-ui classes bind to by class name, plus `#loaddata`: the tile
  images and sounds that `Majiang.UI.pai` and `Majiang.UI.audio` clone from. A route that needs
  neither may replace the body; one that draws tiles keeps `#loaddata`.
  The initial loading screen and its critical styles live inline in the HTML so they appear before
  JavaScript or the board styles arrive. Tile routes decode their images before rendering; the live
  game dismisses the screen after its start event or reconnect snapshot has drawn the table.
* Vite builds with base `/game-assets/`; the lobby answers the game pages with `dist/index.html` and
  serves `dist/` under `/game-assets/`, or proxies both to this app's Vite dev server under
  `make run-local-server` (`frontend/AGENTS.md`, Tooling).
* Static assets live in `public/` and are referenced by absolute path (`/img/…`, `/audio/…`), which
  Vite prefixes with the base in dev and build alike. A relative path skips the base and breaks.
* Styles are upstream's Stylus sheets: `index.styl` for the board, `pages.styl` for the replay,
  storybook and missing-session pages, both imported by the entry. `#board` is a full-bleed felt
  stage filling the window below whatever sits above it; inside it, the table (`#board > .board`,
  a fixed 800px layout) is scaled up or down by `Majiang.UI.Util.scale` to fit, centred, except
  on an upright touch screen, where it rests on the stage's bottom edge for hand reach. The
  settings gear is a HUD pinned to the stage's top-right corner, outside the table: the right
  player's melds reach that corner of the table, so when the side felt is too narrow for the gear
  the fitter either narrows the table or leaves a strip above it, whichever keeps it larger. The
  result and standings dialogs dim the whole stage through one layer on the table that reaches
  past its edges, so the table does not clip its overflow.

## App

* **Routes** (`src/js/routes.js`, dispatched by `main.js`): the live game, the replay and the
  storybook. Any other path goes back to the lobby. The lobby lists each game page path with its
  login policy (`backend/lobby/server/app.py`) and 404s any other, so a new route needs its path
  added there.
* **Globals:** majiang-ui and the ronin layer read the upstream globals `Majiang` (core, plus `.UI`)
  and `$`/`jQuery`, which `majiang.js` sets. It stays the first import of `main.js`: modules that
  read `Majiang` at load time evaluate after it.
* **Handoff:** the game page reads the socket URL and ticket only from the lobby's `sessionStorage`
  entry (key and shape in `docs/architecture.md`); credentials never come from the URL. Without one
  the page says so and links to the lobby.
* **Live game:** `ronin.js` builds majiang-ui's `Player`, `Board` and `GameCtl` and connects them to
  the ronin layer. The session joins with the ticket, reconnects with backoff and resumes the seat
  with the same ticket, and sends the player to the lobby on a permanent join or reconnect error.
  Server events are translated into majiang-core model events the UI plays as if it ran the game
  itself; the UI's decisions are translated back into wire actions. A client-side shadow of the
  seat state supplies what the translation needs and the wire messages omit: physical tile ids,
  other seats' hidden draws and the live wall count.
* **The server judges every decision.** majiang-core's own rule checks never decide a button: the
  player (`src/js/ronin/player.js`) offers exactly what the server offered (a draw's available
  actions, a call prompt's calls), because the server refuses an action it did not offer and
  disconnects a seat for an impossible one. A call prompt, a chankan prompt included (it precedes
  its kan's meld event), reopens the decision on the discard the model already played.
* **Wait ids:** every action echoes the wait id of the last server message that carried one (a
  draw, the seat's own pon or chi, a call prompt, a round end, the reconnect snapshot). A round end
  without one is the game's last: nothing is confirmed, and the final standings wait until the
  player dismisses that result. A refused action reopens its decision; a stale one does not.
* **Reconnect:** the `game_reconnected` snapshot rebuilds the table; on the seat's turn the server
  re-sends the draw already in the snapshot's hand, so a draw of a tile the hand holds only reopens
  the turn. The round's number within its wind comes from the first dealer, which the snapshot
  gives only as the dealer dice. The final standings' ledger (the shadow's round logs) is seeded
  from the snapshot's round history, as reduced round logs holding only what the standings read.
* **Protocol:** `src/js/ronin/wire.js` mirrors the wire enums of `backend/game/messaging/` and
  `backend/game/wire/`; change both in the same change. The client sends no heartbeat: liveness is
  the WebSocket protocol ping (`docs/architecture.md`), and the server refuses unknown message types.
* **Turn countdown:** only the seat's own decisions are counted down, in majiang-ui's timer above
  the right end of the hand: a turn's base time beside its bank (`5+30`), then the bank alone, a
  call prompt's fixed time. `TurnClock` (`src/js/ronin/clock.js`) keeps the bank from the timer
  settings of `game_started` or the reconnect snapshot and mirrors the server's pacing rules,
  never re-synced: a decision runs from the server message that opens its wait to the one that
  ends it, because a refused answer leaves the server's timer running. An own kan is the
  exception: its meld waits out other seats' chankan prompt, so the clock holds at the answer
  (and runs on if it is refused). A countdown that runs out stops at 0 and does nothing else: the
  decision stays open until the server's timeout plays the default, never majiang-ui's default
  reply (a riichi discard, say), which could reach the server before its own deadline.
* **Silence watchdog:** since the client sends nothing on its own, a socket whose peer vanished (a
  FIN lost while the device slept) never fires `onclose`. `RoninSession` treats a server silent
  longer than any legitimate wait as a drop and reconnects, measured on the wall clock so the first
  check after a wake sees the whole gap. The limit is hand-derived from the session `TimerConfig`
  defaults (`backend/game/session/AGENTS.md`, Pacing) plus a margin for late timers; re-derive it
  when the pacing changes.
* **Replay:** the page fetches `/api/replays/{game_id}` and shows its raw text; there is no viewer.
* **Storybook:** renders majiang-ui's own components (tiles, hands, melds, rivers and the board)
  and a persistent loading preview cloned from the startup screen's HTML, using its shared styles,
  from fixed sample states in `storybook.js` and `storybook/`; the board pages reuse the page's
  `#board` markup and fit it below their header with the same `Majiang.UI.Util.scale`. The
  in-round and round-end pages feed their states the way the ronin layer does (`RoninPlayer` with server-style offers, `translate.js`'s round-end shapes), so they
  show what a player sees; keep them in step when that layer changes.
* The game UI's text is upstream's Japanese; the pages written for ronin (replay, storybook) are
  English.

## Conventions

* Upstream code (`src/vendor/`, `majiang.js`, `ronin.js`, `src/js/ronin/`, the Stylus sheets,
  `index.html`) keeps its own style: oxfmt ignores it (`.oxfmtrc.json`) and ESLint relaxes the rules
  it trips (`eslint.config.js`). Code written for ronin is formatted by oxfmt and linted in full.
* ES modules only (`"type": "module"`), `src/vendor/` included.
* The app is plain JavaScript, so `bun run typecheck` is a no-op.

## Tests

Vitest with happy-dom. New tests go in `src/js/__tests__/`. The `describe` block names the subject
(the module or function under test) and the `it` title says what it pins.
