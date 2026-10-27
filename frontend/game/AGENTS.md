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
* Styles are SCSS in `src/styles/`: the board, its 800×680
  desktop layout and its 800×450 tablet layout (only inside the `height <= 450px` media query), then
  the replay, storybook and missing-session pages. The tile, hand and river boxes are sized by the
  mixins of `_pai`, `_shoupai` and `_he`, named after upstream's classes. `#board` is a full-bleed
  felt stage filling the window below whatever sits above it; inside it, the table (`#board > .board`,
  a fixed 800px layout) is scaled up or down by `Majiang.UI.Util.scale` to fit, centred, except
  on an upright touch screen, where it rests on the stage's bottom edge for hand reach. The
  settings gear is a HUD pinned to the stage's top-right corner and the auto switches one pinned
  to its bottom-left, beside the hand: the gear stays off the table, whose top-right corner holds
  melds, while the switches may also cover the table's felt left of the left player's hand, whose
  box on the tablet layout runs nearly the table's whole height. When there is too little room for
  them the fitter either narrows the table or leaves a strip above it for the gear and one below it
  for the switches, whichever keeps it larger. The
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
  it recovers the handoff from the lobby (`GET /api/game-session`, `game-session.js`) and stores it
  under the same key; a player with no game is told so and linked to the lobby, a failed lookup gets
  a reload link instead, and a different live game sends the page to that game. A recovered ticket
  joins like a delivered one, falling back to RECONNECT once the game plays.
* **Live game:** `ronin.js` builds majiang-ui's `Player`, `Board` and `GameCtl` and connects them to
  the ronin layer. The session joins with the ticket, reconnects with backoff and resumes the seat
  with the same ticket, and sends the player to the lobby on a permanent join or reconnect error.
  Two closes are permanent too and cancel any retry, a scheduled RECONNECT retry included: 4002
  `replaced_by_new_connection` (another socket of the seat, usually another tab, took it over;
  reconnecting would take it back, forever) and 1008 (the server kicked the seat for an impossible
  action; reconnecting would loop through kick, AI turn and restore). Any other close reconnects,
  1000 `game_ended` included: after the game end it stays closed, and without one the reconnect's
  refusal leads to the lobby.
  Server events are translated into majiang-core model events the UI plays as if it ran the game
  itself; the UI's decisions are translated back into wire actions. A client-side shadow of the
  seat state supplies what the translation needs and the wire messages omit: physical tile ids,
  other seats' hidden draws and the live wall count.
* **The server judges every decision.** majiang-core's own rule checks never decide a button or a
  selectable tile: the player (`src/js/ronin/player.js`) offers exactly what the server offered (a
  draw's available actions, riichi's tenpai-keeping discards included, and a call prompt's calls),
  because the server refuses an action it did not offer and disconnects a seat for an impossible
  one. Discards are the one fixed rule the client applies: any tile in hand, in riichi only the
  drawn one. The turn after the seat's own pon or chi opens with the server's `turn` event, not with
  the meld, and its kuikae types are the tiles it blocks. A call prompt, a chankan prompt included (it precedes
  its kan's meld event), reopens the decision on the discard the model already played, after
  showing that kan as declared. A robbed kan never gets a meld event: the round end that robs it
  names it (`rk`), and a seat not offered the chankan sees it declared there, before the win's call,
  as does the reconnect snapshot during the round advance. A kan is played into the model once:
  the meld event or round end after a chankan prompt that showed it only updates the shadow.
  Furiten is the server's too: the board shows フリテン above the seat's nameplate from the `furiten` event and
  the reconnect snapshot, and a new deal hides it.
* **Wait ids:** every action echoes the wait id of the last server message that carried one (a
  draw, the `turn` event after the seat's own pon or chi, a call prompt, a round end, the
  reconnect snapshot). A round end without one is the game's last: nothing is confirmed, and the
  final standings wait until the player dismisses that result. A refused action reopens its
  decision; a stale one does not.
* **Reconnect:** the `game_reconnected` snapshot rebuilds the table and opens no decision; when the
  game awaits the seat the server re-sends the event that opened the wait: the `turn` event after
  its own pon or chi, or the draw already in the snapshot's hand, so a draw of a tile the hand holds
  only reopens the turn, or the call prompt, which names the discard it reopens on. Other seats'
  face-down hands are rebuilt to the snapshot's tile counts, a 3n+2 one holding its turn's draw,
  since their draws are not replayed. The round's number within its wind
  comes from the first dealer, which the snapshot gives only as the dealer dice. A snapshot taken
  during a round advance is the round that ended, with its result; it shows the table, and the result
  to confirm only when the snapshot says the seat still owes the confirmation (`oc`), which only a
  takeover of a still-connected seat does: a seat that disconnected during the wait was confirmed
  by its disconnect, and a seat an AI player held at the round end was never required. The final
  standings' ledger (the shadow's round logs) is seeded from the snapshot's round history, as
  reduced round logs holding only what the standings read; that history already holds a round
  that ended, so its replay is logged nowhere.
* **Protocol:** `src/js/ronin/wire.js` mirrors the wire enums of `backend/game/messaging/` and
  `backend/game/wire/`; change both in the same change. The client sends no heartbeat: liveness is
  the WebSocket protocol ping (`docs/architecture.md`), and the server refuses unknown message types.
* **Turn countdown:** only the seat's own decisions are counted down, in majiang-ui's timer above
  the right end of the hand: a turn's base time beside its bank (`5+30`), then the bank alone, a
  call prompt's fixed time. `TurnClock` (`src/js/ronin/clock.js`) keeps the bank from the timer
  settings of `game_started` or the reconnect snapshot and mirrors the server's pacing rules; each
  turn's opening draw or `turn` event names the server's bank (`bk`), which replaces the clock's, so
  one turn's network delays never skew the next. A decision runs from the server message that opens
  its wait to the one that ends it, because a refused answer leaves the server's timer running. A wait re-sent after a
  reconnect names how long its server timer has run (`el`), and the decision is backdated by that
  much, so a taken-over turn counts down what is left and charges the bank what the server does. An own kan is the
  exception: its meld waits out other seats' chankan prompt, so the clock holds at the answer
  (and runs on if it is refused). A countdown that runs out stops at 0 and sends nothing, never
  majiang-ui's default reply (a riichi discard, say), which could reach the server before its own
  deadline: a turn stays open until the server's timeout plays its discard, and a call prompt
  closes, since the server has passed for the seat by then and the next seat's draw, which ends
  the wait, goes only to that seat. The countdown starts after the prompt is shown, so one re-sent
  with its time already run closes at once. A dropped socket closes the open decision the same way;
  the reconnect re-sends any wait the server still owes the seat.
* **Inputs:** each decision binds one default action to a right-click on the board and to Escape:
  a call prompt passes, a choice it opened (a chi, pon or kan variant, a riichi discard) backs out
  to its buttons, a ready round result continues, and the seat's own turn discards its drawn tile
  on a right-click only. A left click on the board answers nothing, so the second click of a
  double-click, or a tap on the felt, never passes a ron that arrived in between.
* **Auto switches** (`src/js/ronin/autoplay.js`): 自動和了, ツモ切り and 鳴きなし answer the seat's
  decisions for it, on the client alone, through the same answer path as a click. 自動和了 declares
  any tsumo or ron the server offers (a chankan included), a ron a second after its prompt with
  the buttons hidden (at once when less of the prompt's time is left), dropped if the server ends
  the prompt first and shown again if the switch is turned off meanwhile; ツモ切り discards the drawn tile only when
  its turn offers nothing else (no tsumo, riichi, kan or kyuushu); 鳴きなし passes a call prompt
  that offers no ron. A switch answers decisions opened after it is turned on, never the one already
  showing, and never a refused answer's retry. They last until the round ends: its round end clears
  them, and so does a reconnect into another round or a round result.
* **Screen countdowns:** the screens the server moves on from by itself count down to it: the game
  start screen its start pause (`gp`) until the deal, and a round result the round advance timeout
  (`ra`) on its 次へ button. A round end shows each result its share of the server's timeout,
  measured from the round end (backdated by the snapshot's `el` after a takeover): every result but
  the last dismisses itself at its share, and the last stops at 0 and sends nothing, leaving the
  confirmation to the server's timeout and the next deal. The game's last round end opens no wait
  and counts nothing down. Only 次へ dismisses a result (`RoninPlayer.action_hule`), or Escape and a
  right-click once its dialog is ready, not a click elsewhere on the dialog: a stray discard click as
  it opens, or a tap to scroll it, would skip it.
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

* Upstream code (`src/vendor/`, `majiang.js`, `ronin.js`, `src/js/ronin/`, `index.html`) keeps
  its own style: oxfmt ignores it (`.oxfmtrc.json`) and ESLint relaxes the rules it trips
  (`eslint.config.js`). Code written for ronin is formatted by oxfmt and linted in full.
* Styles: `styles/game-app.scss` is the one entry stylesheet; partials load with `@use`, never
  `@import`. Use the colour and font variables of `styles/_theme.scss` rather than literals; only
  colour keywords and translucent `rgb(… / alpha)` overlays stay inline. Divide with `math.div`, never `/`.
  Class names are kebab-case (BEM `__`/`--` allowed), as the lobby's: a class the JavaScript or
  `index.html` sets is renamed there too. Stylelint runs a copy of the lobby's config (keep the two
  in sync), which lets `-webkit-text-size-adjust` through because iOS Safari still needs it.
* ES modules only (`"type": "module"`), `src/vendor/` included.
* The app is plain JavaScript, so `bun run typecheck` is a no-op.

## Tests

Vitest with happy-dom. New tests go in `src/js/__tests__/`. The `describe` block names the subject
(the module or function under test) and the `it` title says what it pins.
