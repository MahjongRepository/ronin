# Game client v2 (TypeScript / lit-html)

The earlier game client SPA, restored as the foundation of a future client: the lobby serves it
instead of `frontend/game/` on any game page whose query has `v=2` (`/play/{game_id}?v=2`,
`/play/history/{game_id}?v=2`). Its protocol layer parses the current protocol and replay format,
but the views act on less of it than v1 does: the live game plays its decisions on the board (the
discard, the offers, pass, the countdown and furiten) and the round results the player confirms, with
each seat's nameplate around the table.
Adapt the client to the server rather than the server to it. `src/shared/protocol/` and
`src/entities/table/` have their own `AGENTS.md`.

## Build

* `index.html` is the app's page and `src/index.ts` its entry. Vite builds with base
  `/game-assets/v2/`; the lobby answers a `?v=2` game page with `dist/index.html` and serves `dist/`
  under `/game-assets/v2/`, or proxies both to this app's Vite dev server under
  `make run-local-server` (`frontend/AGENTS.md`, Tooling). The lobby never adds `v=2`, so open the
  first page with it by hand; the client's own links to its pages (another game's page, a game's replay)
  keep the page's query, and with it the parameter.
* `npm run sprite` (Node runs the TypeScript script directly) rebuilds the tile sprite from the
  tile SVGs after one changes; the sprite is committed. `entities/tile/lib/tile-config.ts` is the
  single source for the active tile set. The sprite ships as an asset of its own, cached apart from the
  code: `index.html` preloads it, `index.ts` fetches and injects it before the first route mounts, retrying
  a failed fetch with backoff and again when the browser comes back online (`loadTileSprite` over
  `shared/lib`'s `startRetryingLoad`, IO the entry owns), and a face drawn before it lands shows once it does. Until then each face shows its short
  name (`5m`, `E`), so a tile is never blank; the live game's board says so with a reload while a load
  has failed (`PlayUi`'s sprite status, which the driver keeps from the loader, never the dispatcher).
* The one face is Inter, self-hosted: `src/assets/fonts/inter-latin.woff2`, a Latin subset with its own tabular
  figures (how it was cut and from which release in `SOURCE.txt`, the licence in `OFL.txt` beside it). `_theme.scss`
  declares it with `font-display: swap`, so text never waits on it (a countdown reads at once), and `index.html`
  preloads it like the sprite, so it usually lands before a board does; a glyph outside the subset (a name in another
  script) falls back to the system sans-serif after it in `--ronin-font`.
* `package.json`'s `sideEffects` names the only modules with an import-time effect (the stylesheets,
  `zod-setup.ts`), so the build drops a module none of a route's code uses even when a barrel
  re-exports it: the replay's and the scenarios' modules stay out of the entry. A new module with such
  an effect is added there, or the build drops it.
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
  leaving its queue stuck, and reports a socket factory that throws as a failed connection. A
  protocol failure never throws out of the dispatcher (Desync), so what does is a bug in the client.
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
  none, does nothing, so a stale timer cannot act. A valid event the dispatcher otherwise ignores
  (a socket error, an intent with nothing to answer) is not a tick: it advances `now` and runs the
  expiry and the resync settlement every event runs, so it can send a resync request that came
  due, but only a tick drives the session's deadlines (a connect timeout, a retry). An event tag
  the client does not know is a bug, thrown as an ordinary error (`assertNever`); malformed wire
  input puts the client out of step through parsing (Desync), and a recognized message the table
  cannot take throws a `DesyncError`. Display-only data (the game view's debug log) stays in the
  view, out of the state.
* **One client state.** The dispatcher composes the session, the table (`entities/table`) and the
  viewer's interaction into one immutable state: the viewer's seat, its open decision, its
  furiten, the timer settings, the round confirm it owes, when the first deal is due, the calls
  the board shows, the play switches the player turned on and the highest wait id the game has opened. A replay is the same state with no
  session and no viewer; visibility (a replay's every hand, a live seat's own) is what the source
  showed and how the board is drawn, never a second model, and the seat at the bottom is the
  view's choice (the replay's is the recorded first dealer's, `docs/architecture.md`, Replays).
* **Decisions.** A decision opens only from a message carrying a wait id to the viewer's seat (its
  draw, its `turn` event, its call prompt), with the offers the server listed and nothing the
  client judged but the discard rule (kuikae, riichi's drawn tile). Its deadline is the client's
  estimate of the server's timer, in logical time from the timer settings and the bank the opening
  message names (none when it names no bank), backdated by a re-sent wait's elapsed time, so a
  countdown reads from `now`, never the wall clock. A turn also keeps when its base time runs out
  (the elapsed time comes off the base first), so its countdown shows the base and the bank apart, then
  the bank alone, marked and announced, as the server drains it; a reconnect's re-sent wait resumes
  both where the server stands, never a fresh full turn. Past it the decision shows as expired, for
  display only: the server alone decides by the wait id whether an answer counts, so an expired
  decision still takes one answer, and the client never answers without the player's instruction,
  standing (a play switch) or given (a press). Answering sends the action with the decision's wait
  id once and marks it submitted with the intent it took, which the display reads for the tile
  played and the control that answered, never the wire message; the server's next move closes
  it, a refusal while its wait goes on (a game error but a stale one, or the socket's rate limit)
  reopens it, and a dropped socket drops it, since the reconnect re-sends a wait the server still
  owes the seat. A refusal counts only when it names the decision's wait id (`refusalOf`): the rate
  limit can answer an older frame after the game moved on, so one naming no wait or another wait
  reopens nothing and shows no notice.
* **Play switches** (`model/play-switches.ts`): Auto win, No calls and Auto discard are the player's standing
  answers, a field of the client state. Turning one (the `toggle_switch` intent, taken only on a live seat while a
  round plays) sends nothing; the dispatcher answers for it where a message opens a decision on a wait id above the
  highest one a decision of the game opened before (`highestOpenedWaitId`), since the server raises the id only when
  a call ends a wait (a partial prompt response and a refusal keep it), stepping the switch's intent exactly as the player's
  press would be stepped: the same send with the decision's wait id, once, marked submitted with the switch that sent
  it (`bySwitch`). So the decision already open when a switch is turned on, a wait the client saw before, re-sent
  after a reconnect, and a decision a refusal reopened are never answered by a switch. The mark rises with every
  opened decision, the switches on or off, and is never lowered; it is kept across a drop (which drops the decision
  itself), a refusal and a deal, forgotten only on a table of another game, and never taken from a snapshot's `wi`:
  a wait the server opened while the socket was down is new to the client, and a switch answers it when the
  reconnect sends it. `switchAnswer` is the policy (the spec's Play switches): a win first (a turn's tsumo, a prompt's
  ron), then No calls' pass of a prompt offering a call and no ron, then Auto discard's discard of the drawn tile on
  a turn offering nothing else (`TurnDecision.drawnTileId`, null on the turn after the seat's chi or pon); no timer,
  since ron is taken at once. A deal turns all three off, as does a reconnect's snapshot that leaves the hand
  (`snapshotLeftHand`): one of another game or another deal number `n`, or where the table before it or the snapshot is
  not in a round. A snapshot of the hand's own result pending keeps the hand's `n`, so only its phase tells it left the
  hand. A snapshot of the same hand keeps them, and a reload starts with them off. A decision No
  calls passed shows no controls; one Auto win or Auto discard answered shows as answered. The board shows them
  (`PlayDisplay.switches`) only while the dispatcher takes their intent, never on a replay board.
* **Round confirm.** A round end's wait, or a reconnect's snapshot of a round advance that says the
  seat still owes it, opens the round confirm like a decision: one confirm intent sends it once with
  that wait id, then the seat waits for the others. Only the next deal (the last confirm's or the
  timeout's) closes it, and only a refusal naming its wait id reopens a sent one, as it does a
  decision; a late refusal of an earlier move names that move's wait, and the confirm's own stale
  reply follows the deal that closed it. A dropped socket drops it, since the snapshot says again
  whether it is owed. Its deadline is one per round, armed at the round end: the round advance timeout times
  the result's pages (the server's `results_shown`, a double ron's winners), backdated by the
  snapshot's elapsed time, and none when the snapshot names none: never a fresh full timeout. It is
  display only, shown labelled and kept while the seat waits: the client never confirms on its own
  and arms no timer for it. A double ron's pages each show Next until the last, which alone
  confirms, so the player has seen every winner before confirming. The game's last round end
  carries no wait and its game end follows at once: the table keeps that result and the live board
  shows it over the standings until the player dismisses it, which sends nothing; the standings'
  Last hand (the `show_last_result` intent) reopens it, on its first page, sending nothing either.
* **Desync** (`model/desync.ts`). A protocol failure puts the live client out of step with the
  server: a server message that does not parse, a frame the socket could not decode
  (`frame_undecodable`, apart from the browser's socket error, `transport_error`, which only its
  close follows), or a message its table or decision cannot take, which they report by throwing a
  `DesyncError` (`entities/table`); a silent fallback that guesses (an offer dropped for want of its
  tile) is one too. Out of step, the client answers nothing, drops the open decision and an owed or
  sent round confirm, never resends what it sent, and keeps `highestOpenedWaitId`, so a wait re-sent
  after the snapshot is the player's to answer; the session still takes every message, but only the
  snapshot, the game's end and the round end before it (the game's last, which carries no wait)
  reach the table, every other message dropped. Those two carry the scores and the result the server
  settled, so a game that ends out of step ends on them, but the table records the loss of step
  (`lost_step`), dropping any result it kept, so only a result taken in step or that last round end
  opens the final result, its panel noting what may be wrong, and the standings mark their ledger
  incomplete (`entities/table/AGENTS.md`); a last round end it cannot take is one more message
  dropped. It sends one resync request on the open
  socket and again only once one goes unanswered for `RESYNC_ANSWER_MS`, or, refused because the
  game has not dealt yet, when the first deal is due (`firstDealDue`); a dropped socket forgets the
  request, since the reconnect's own snapshot rebuilds it. A snapshot it takes puts it back in step
  and alone resets the board's count of failures (`unreadMessages`). A second snapshot that answers a
  request sent again can follow the player's answer to the first one's wait: a snapshot or re-sent
  opening naming the wait of a submitted decision or a sent round confirm leaves it submitted, so the
  wait is never answered twice. The requests are counted for the page, never reset by a snapshot or
  the session's admission, so one past `MAX_RESYNC_REQUESTS` ends the page as failed, as does a
  snapshot that does not parse or that it cannot take, or a game's end it cannot take. A server
  message or an undecodable frame that arrives while the session has no open socket (it recovers
  its handoff, connects, awaits a transport retry or ended) is dropped, as the session drops it. An error
  that is not a `DesyncError` is a bug and propagates to the driver.
* **Game start and calls.** Before the first deal the board's panel is the seating (`gameStartDisplay`):
  the game's length and first round, each seat's wind and player, the dealer, AI players and the viewer
  marked, and the server's game start pause counted down (`firstDealCountdown`, from the game start's
  timer settings), or only "Starting…" where none is known or it ran out. A call (chi, pon, kan of any
  kind, a riichi declaration's discard, ron, tsumo, a triple ron's three rons) shows by its seat for a
  moment, from the dispatcher's state (`calls`): a table event's calls (`eventCalls`) replace the
  ones shown. A kan is called once, when the table first shows it: neither the meld that completes a kan
  its chankan prompt showed nor the prompt a reconnect re-sends calls it again, however long the prompt
  waited, while another kan of the same seat is called afresh. A live message's last `CALLOUT_MS`
  (`entities/table`, which the board hands its stylesheet as `--callout-ms`) or until a newer
  call, never ended by a move that calls nothing, since one may follow at once (an AI player's discard
  after its pon, the viewer's draw after a riichi), nor by the game's end, so the last win shows its call;
  a failed or left session drops them. Each lies over its caller's river at the first of a few fixed spots
  (in river tiles and rows, `CALLOUT_SPOTS`) clear of the latest discard's row (top, bottom) or column pair
  (sides), its chip no taller than a river row (its font bounded by the row, its pop never past full size),
  so it never covers the action source, a control or the own hand. A replay line's last until the next move, so each
  stop shows its own move's calls and stepping or autoplay leaves none behind. The board keys each
  showing, so a new one replays its CSS animation and a redraw does not; it takes no input, and a
  win's call shows before the result panel, which waits for it by CSS alone; the board waits only when
  told its panel is a result (`overlayIsResult`), so the leave question and an end show, and take the
  focus, at once. The seat in turn is cued only by the centre's bar on its side and its badge's
  underline (the spec's turn cue), the viewer's turn and call prompt by nothing else; furiten shows only
  while a round plays, as a dot and the word in its slot by the hand (`GameBoard`'s `furiten`).
* **Final standings** (`boardOverlay`, live and replay alike): the seats in the server's placement
  order with its uma/oka results, the ledger of every finished round with a line saying what its marks
  mean, the leftover sticks, the viewer's seat (the live seat, the replay's bottom seat) marked. Their
  panel, mapper and stylesheet are a lazy chunk (`startStandingsLoad`, with the sprite's retries), which
  each view that may show them starts as it mounts and stops on dispose; the view hands the loaded
  renderer to `boardOverlay`, which shows no standings until it has one, and a board notice says so once
  every try failed. The live standings lead to the
  last result, this game's replay from the player's seat (the page's `v` kept), the game history
  and the lobby (the leave intent); the view is given the links (`GameLinks`). The replay's lead
  to the game history and the lobby, and each round's row is a button to its result
  (`roundResultCursor`), after which the focus returns to the replay's root, so its arrow keys go on.
* **Timelines, not history in the driver.** `buildClientTimeline` steps any event sequence into
  the state after each event; stepping back selects an earlier state, never an inverse event, and
  nothing in a timeline executes an effect, so revisiting a prompt sends nothing and arms no
  timer. The replay view reads its file into such a timeline, and each of its stops is one of the
  timeline's states. Reading stops at the file's first line that does not parse or that the table
  refuses, since every later state would build on a table that missed it, and the page labels such
  a replay damaged, as it labels one whose recording ends before the game's end incomplete. The
  dispatcher takes one event in one step, except a replay's round end that
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
  makes terminal (its own copy of the codes) and after the game's end, and nothing from any other tick, so an automatic send that is
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
  a `BoardDisplayState` with slots for an overlay, the local hand's input and a place by the hand for
  the decision's controls, and decides nothing. `tableStateToDisplayState` maps a table from a
  perspective; `playDisplay` (`entities/client`) maps a whole client state for the live board: the
  table from the viewer's seat with only its hand face up, each of its tiles marked by the open
  decision (selectable, declaring while the riichi toggle is on, held back, the one an answer played), the
  intent each selectable tile sends, the decision's controls ranked (`DecisionAction.rank`: the wins, ron,
  tsumo and kyuushu, first; then riichi as one toggle and one control per other kind of offer in the
  server's order; then a pass), the countdown, where the decision stands (open, expired, answered), what
  Escape does, furiten, a chankan offer's kan (`sourceMeld`), and the round result's controls
  (its one primary button, the result's pager only secondary beside it, the countdown, waiting for
  the others). What may be played is never
  restated there: every tile intent and button is one the dispatcher's own `takesIntent` takes (the
  decision's answer on a socket it can send on), so the board offers exactly what stepping the
  intent would send. `PlayBoard` only renders that, with the table's panel over it, and routes a
  command: an intent goes to the dispatcher; the view state is `PlayUi`, an input of the mapper too:
  the riichi toggle and a call's choice of tiles, each keyed by the decision's wait id so a newer decision
  never inherits it, each turning the other off; and the
  round result's page, keyed by the round the result ends (its wind, dealer and honba, which a
  reconnect's snapshot names alike), so a newer result opens on its first page while a reconnect
  keeps the page; and the nameplate pinned for score differences. A kind of offer with a choice of tiles
  (two chi, two kan) is one control that opens its second step, which is that control pressed, each
  choice the dispatcher takes as a tile group laid by `meldTiles` as the meld will lie, the pressed control
  after them (where the first step had it, so pressing it never moves it; a desktop row shows it first), and
  Back in Pass's place; Back, Escape (the board's) and the call pressed again go back, Escape moving a focus it finds on a
  decision control to the call's control, and Escape also turns the riichi toggle off. One Escape is one step:
  a pinned badge's unpinning first, and never an Escape a panel over the board already took (the leave
  question's). An answered decision keeps the controls it was answered from, inert, the one whose answer
  matches the sent message marked, and its steps no longer change, so nothing moves while the server
  answers. One gesture serves every board
  (live, replay, storybook): hovering a nameplate, or tapping it (a button, so a key too), shows the
  other seats' scores in the centre as differences from its own; a tap pins it until it is tapped again, another
  part of the board is tapped or Escape is pressed. The replay's viewpoint switch is a control of its
  own, never the nameplate's tap. A new prop on the board is added to these mappers
  when a scenario shows the need, never computed in a view.
* **The replay page** opens where its address says, else on the first deal, and moves only
  through the table slice's cursor functions (`entities/table/AGENTS.md`); its view state is the
  cursor, the seat at the bottom, the round list's openness, the pinned plate, autoplay and whether
  the other hands hide. Autoplay's state is plain data and its pacing a pure function of the stop and
  speed; the view arms one clock timer to it. Autoplay, a held step button (repeating from a pointer's
  press, under its capture, waiting while the pointer is off it) and a turning wheel all pause where a result shows
  (each page of a double ron) and at the end, and autoplay also stops on any move the reader makes, as
  the page hides and on dispose; any other move and autoplay's start end a hold. A press's step is its own, so
  only the click that press ends in is dropped, never a keyboard's or an assistive technology's. The wheel steps by gesture, not by event (`shared/lib/wheel-steps.ts`):
  a first step at a mouse notch's distance, then each further stretch and beat, a rest or a turn back
  starting over. Keys are the root's: arrows step and move rounds, Home/End go to either end, Space
  switches autoplay except on a control it activates itself, V and H (by key position) switch the view
  and the hands, each switch once per press; Enter and Space on a step button are that step, prevented
  so the button never clicks too, and so held they pause as a held arrow does; a field, an input method's
  composition, a modifier, the round list's and the standings' own keys and the keys that scroll a round's
  result scrolling in its panel are never the page's. A render that takes away or disables the focused control
  gives the focus back to the root. The viewpoint switch moves the seat at the bottom and the address's
  `seat`, never the cursor or a result's page. Hiding the hands draws the board and the narration as
  the bottom seat sees them. That and autoplay's speed are the reader's settings
  (`entities/table/model/replay-prefs.ts`, `localStorage` read and written in try/catch, the defaults when it
  is blocked), never the address: the address names a position, and a shared link imposes no way of
  reading it. Its IO stays at
  the edge, given by `index.ts`: the load, which asks again on 404 after 500, 1000 and 2000 ms (the
  game end reaches players before the server saves the replay) and is aborted with its waiting
  retry on dispose; and the address, kept on the position shown with `history.replaceState` at most
  once per 500 ms (Safari's history limit), the page's other parameters (`v=2`) kept, a waiting
  write flushed as the page hides and dropped on dispose, since a dispose follows a navigation. A
  replay it cannot show (not found after the retries, refused, unreachable, another version, no
  deal) gets a screen saying why with the way back to the game history and the lobby, and a retry
  where one may help: only a failed fetch counts as unreachable, while a throw in reading or drawing
  the replay says it cannot be shown, its error on the console, with no retry. The wheel steps only
  over the board, outside the round list, the standings' rounds and a round's result scrolling in its
  panel, and only where a step goes; anywhere else it scrolls. The narration is read out by a live region
  of its own, polite and left empty while autoplay runs.
* **Session** (`entities/session`): one machine owns finding the handoff, joining, playing,
  reconnecting and the end. It joins with the lobby's ticket (`shared/session` holds the handoff) and
  resumes the seat with the same ticket. A tab that holds no ticket asks the lobby
  (`GET /api/game-session`) through an effect the driver runs and cancels on dispose: this game's
  handoff is kept and joined with, another game's kept and its page opened (the query, so `?v=2`,
  carried over), none sends the player to the lobby, and a failed lookup is asked once more after a
  short wait (`policy.ts`), then stays on the page with a reload. An active session is one of four
  states, each a variant of its own carrying only its own facts, so no combination of flags implies
  one: connecting (a socket asked for, with its connect deadline), identifying (the socket open and
  the identity message sent, JOIN_GAME or RECONNECT, with a session retry's due time or none),
  playing (the seat held: the only state that sends game messages, and the only one without an
  identity or retry count) and awaiting a transport retry (no socket, with its due time). Whether
  this page lost the seat it held belongs to the RECONNECT identity alone, so a join never has lost
  one. Only an open socket carries a message, so connecting and awaiting a retry ignore every one.
  A refusal ends any active session; only identifying schedules identity retries:
  `join_game_already_started` turns a JOIN_GAME into RECONNECT and is ignored once the session
  reconnects or plays, and `reconnect_retry_later` (to a RECONNECT) and a rate limit schedule a
  session retry. Any other handling of a session error (a rate limit or `game_not_started` answering
  a resync request or an action) is the client's. Two retries stay distinct, each with its own
  backoff and budget: a transport retry reopens a dropped socket, a session retry resends the
  identity message on the open socket. A drop supersedes a waiting session retry, since the reopened
  socket sends the identity message itself. A socket that has not opened by its connect deadline is
  closed and retried as a drop. Being out of step
  (Desync) is the client state's, not the session's: it concerns the table the session's messages
  build, its resync requests are counted for the page across the session's admissions, and it ends
  by a snapshot the session takes like any other. The stop policy follows the
  server: the 4002 and 1008 closes, a refusal that means the ticket will never hold the seat again,
  and a spent retry budget end the session, cancel its retry and forget the handoff, and stay on the
  page, whose board says why with a way back; a game end ends it on the page and forgets the handoff,
  since its ticket will never hold the seat again; any other close is
  retried, 1000 included (`docs/architecture.md`, Game client contract). A valid input the machine
  has no transition for in its state changes nothing and asks for nothing. An ended session ignores
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

The board's target is `docs/game-client-look.md`, which wins where it and this section disagree; what
follows holds through the rebuild to it.

* **Browser floor: iOS Safari 16.4** (range media syntax; container queries need 16.0, `dvh` 15.4),
  and the smallest supported landscape is 667x375 (iPhone SE 2nd and 3rd generation): the 568x320
  phones never got iOS 16.4, so they are below the floor. The board's sizing rule needs CSS `round()`
  (Chrome 125, Firefox 118, Safari 15.4) and `@property` (Safari 16.4).
* **The live game's page** is the board alone: the page's own controls (`GameMenu`: the way back and the
  session's status as a dot, with one short word by its tone unless connected (a short board, too narrow for a
  word, shows the dot alone, never part of the word), the player's whole wording in
  its title and read out, the notices saying more) sit in the board's top-right corner, so a phone gives the
  board its whole width; `PlayBoard` draws them when given the status, the decisions storybook too. A panel
  over the board leaves the corner clear: the corner is capped to a
  reserve the overlay keeps free beside the panel, on the corner's side alone on a short board, and the
  overlay's tiles size from the width left (`game-board/_overlay.scss`); an upright board does not keep it
  clear yet. The board carries the notices
  (`playDisplay`'s, in the table's own area, never over a tile, a plate, a decision control or the panel, however
  long they stay): a
  seat this page held and lost to a drop while it reconnects, or a connection failing since the page
  opened, each worded the same across its retries so it is announced once (a page that only resumes
  its seat, a reload, shows neither); short-lived ones held in the client state with a logical-time
  expiry (the seat back after a snapshot of such a drop, which a second drop replaces, and a refused
  move, shown only for the refusal that reopens the request it names); and the protocol failures since
  the last snapshot (App, Desync), on the console too, shown until a snapshot rebuilds the table, which may be wrong until then; and tile faces that did not load, with
  a reload, until a retry loads them. An end that stops the session on the
  page blocks the board, and takes the rotate panel's place, with why and a way back. The notices' place is
  the left field under the left badge, outside every river's capacity, scrolling a stack taller than it
  (never clipped silently; "Show all" is Step 4's); a desktop panel over the board then starts past the left
  river's reach, and over a short board's panel they move to the reserve under the right strip's end. With `?debug` (any value but `0`, `false`, `no` or `off`) the corner adds the debug log, a
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
  derives from its box (container query units), never the viewport, so a page that gives it a box
  (`.board-page`) decides its size alone. The spec's sizing rule (`docs/game-client-look.md`, Proportions)
  lives in `game-board/_grid.scss` alone, as custom properties on the board's layout and its overlay: the
  own tile (36x48 under 520px high, else min(5cqw, 10cqh), capped by a full hand's row beside its badge's
  and furiten's slots), the river tile, the core, the centre and every place derived from them (the
  rivers' capacity reach, the foreground band, a badge's place). Its lengths are registered
  (`@property`, `<length>`), so each computes once to pixels where it is set: an unregistered chain grows
  with every reference until a browser drops the declaration. A desktop's core also stays above the
  foreground band's controls and below the top strip's slot; a short desktop (`short-desktop-board`: under
  760px high, at least 1100px wide, such as 1366x657) shares the band's lower corners as a phone does instead;
  an upright board takes the desktop rule, its core bounded by the width left beside two lines of side melds.
  A choice the rule makes between two placements is a length selected by `clamp(0px, x * 1000, 1px)` from the
  viewport's lengths (a full hand's reach, the band's top), never from what a seat holds.
  The perimeter's chrome (badges, counters, the page's corner, callouts) takes a phone's size on a phone,
  upright and on a desktop board under 1100px wide, whose geometry stays the desktop's, and a step larger on
  a board of at least 2000x1200; the top strip's hand starts right of the counters however narrow the board.
  Nothing is measured in script: what content changes a placement (a strip's hand and meld lengths, in
  tile widths) the board hands its stylesheet as custom properties from the display state (`stripStyle`).
  The own hand's tiles are always the board's largest. Every tile's box (its 3:4 from `--tile-w`, the
  room around the glyph, the corners) is `styles/_tile.scss`'s; each region sets `--board-tile-w`. A round
  result taller than its panel scrolls under its foot, which keeps the scores, the primary button and its
  countdown at the panel's bottom.
* **The table** is the spec's composition (Composition, Elements); what the code keeps that the spec does
  not say:
  * Each seat's river and strip is laid in its own frame (left to right from its seat, rows away from the
    centre, a strip's tiles standing on the frame's line toward the seat's edge) and turned into place about
    the frame's corner, so a seat's tiles face it and an added kan's stack lies on its centre-facing side
    at every seat. A river's tiles touch; the pinwheel's gaps (0.3 of a river tile, rounded) part the rivers
    from each other and the centre at every capacity. A side river wraps past its third row into a fourth
    (`Discards`' `wrap`), a top or bottom one runs its third on (`run-on`).
  * An opponent's concealed hand is at the river tile's size, its drawn tile 0.15 of one apart (`--dg`), and its
    full reach (`--full-reach`, fourteen tiles and that gap) has a fixed place per viewport that nothing else
    enters: the left hand runs down from below the counters and the play switches step in past its depth
    (`--switches-clear`) where it would meet them; the right hand's origin (`--right-origin`) is the band's top
    under the corner, else the top margin with the corner stepped in (`--corner-shift`, which the top badge's
    room and a panel's corner reserve also take), else under the corner across the band, whose phone row then
    ends before it (`--band-shift`, which a short board's notices over a panel follow). The choice asks
    whether the hand from that origin enters the band row's height (its box starts at the band's top), with
    half a pixel's tolerance, so the floor's height keeps two pixels of margin whatever the slots' widths.
    With the corner stepped in, the strip's melds may rise to the top margin only while none is deeper than a
    sideways tile (an added kan's stack would meet the corner). A board without the page's corner (a replay's,
    the board storybook's) reserves none and steps nothing. The top hand stands
    centred, short of a badge's width (`--top-badge-w`) before the corner and right of the counters.
  * A side strip's melds take its line while they fit and its oldest the second line inside it, from the
    foreground band toward its badge, scaled to end before the badge: each meld's place is chosen in CSS
    from the units the board hands it (`--mu-k`), never by measuring. The top strip keeps one line and
    scales its melds down, above the top river and the side badges and right of the counters; the own melds keep 1.2 river
    tiles, scaled down to end before the board's edge (their area is a size container, from the meld units the board
    hands the own row). No meld face goes under 13px wide.
  * A badge's place is fixed per viewport and never reads a tile count: the side badges stand clear of the
    deepest a strip's first line can be (two river tiles), and below the top river's capacity row wherever
    they would meet it (always on a phone), the right one level with the left unless that puts it beside the
    right river's rows (the top river's row never reaches that side); a side badge beside its river's rows
    ends before its reach. The own badge has its slot at the start of the own row, whose hand starts where a full hand's
    would, whatever it holds. Badges are the plates' one shape; a long name is shortened in the middle so
    its end shows; an upright board shows the wind and marks alone, its name in the label.
  * The pooled counters (top-left) hold the dora and the honba and riichi counts as icon and number; the
    centre holds the round, the wall's count, each seat's wind and score in a pinwheel row on its side, its
    riichi stick inside the edge, the turn's bar on the edge, and while a badge's differences show, whose.
  * The latest discard (`lastDiscardSeat`, `entities/table/AGENTS.md`) is ringed with a notch on its far side,
    in its river's frame, in the table's neutral latest colour; a claimed tile has left the river. A chankan
    offer's kan is ringed whole in its meld (`meld--source`) until the offer resolves.
  * The decisions' place (`_decision-controls.scss`): on a desktop one row in the foreground band, from past
    the play switches' slot (`--switches-left`/`--switches-right`, on the band's side away from the decisions) to
    the own row's right end, the timer's fixed slot (`--timer-w`, a
    caption line over the digits: Time up, Sent, Bank) last; a row too narrow for its controls (a narrow
    desktop's) wraps the higher-ranked above the band's control and the timer, and four or more under 800px
    shed their tile previews and spare width. A short desktop's row starts past the bottom and right rivers'
    capacity reach and always stacks the higher-ranked above the band's control and the timer, padded clear
    of the right strip as drawn (`--upper-clear`, from `--right-depth`); the band's control wraps above the
    timer where the row cannot hold both, padded the same. A control's tiles stay inside the band's row room
    (`--row-room`: the control's height and the band's slack less the 4px kept from a tile), so the river's
    growth on a large board never brings a control within reach of the bottom river. On a phone the
    lowest-ranked control that is neither a win, a choice of tiles nor a call's first step takes the band row beside the timer (the riichi toggle among them), starting past the own river's
    capacity reach; the rest stack upward, right-aligned, between the right river's capacity reach and the
    right strip as drawn (its second meld line counted, from the per-meld units `rightStripStyle` hands the
    stylesheet), a win or a choice across the column, and pair up, shedding their tile previews, where the
    column (a size container, `decisions`) is too short for one a row (the count `data-upper`). Rings lie
    inside a control's box. The board's container is named `game-board` and its viewport mixins query it by
    name, so a container inside the board never answers them.
  * The play switches (`_play-switches.scss`) stand in their slot on the band row, bottom-aligned with the band, their
    height `--switch-h` (which the left hand's reach is measured against):
    each a native button with the switch role and `aria-checked`, at least 40x40, its knob over its label on a phone
    and a narrow desktop, before it on a desktop; on and off differ by the knob's side, the track's fill and a mark
    on the track's free side (a bar on, a ring off), never by colour alone. They follow the decision controls in the
    board's order, so Shift+Tab from the hand reaches them; an upright board has no slot and hides them.
  * Own tiles: a held-back tile (kuikae, riichi) is recessed, never darkened: lower, smaller, flat, a dashed
    inner rim, its face and glyph colours kept; while some are held back the playable ones stand raised; a
    declaring or played tile is lifted and outlined in the accent, never into the 4px kept under the band.
  * The zone device is decoration under every layer: lines and field tints from the centre's corners,
    drawn with `hypot`/`atan2` and clip paths from the same lengths. On a landscape board page it and the surface's
    gradient run on under the safe-area insets to the screen's edges the board meets (`--ox`, `--oy`, `--or`, `--ob`),
    never toward an aside beside or under the board (a storybook's lies below, past a margin of the bottom inset), the
    upper lines to the screen's top corners.
  * Text the board scales keeps a 10px floor, a safety limit, never the size to design to.
* **Pages never clip the board.** `.board-page` gives it a definite box, the safe area exactly (sized with
  `dvh` and the theme's `--ronin-safe-*`, which a test can set; the table's surface runs on under the
  insets), and puts the replay's controls below it upright, or beside it in landscape as a compact column
  that scrolls when the window is too short for it. A storybook's switches always lie below the board, so
  its board is the live game's box (36x48 own tile at 667x375) and the page scrolls to them. The replay's controls below (its
  column and bar, its narration's three lines) are the current implementation's, kept until the replay's
  controls move into the board's foreground band as the spec places them. The replay's column is two 40px
  move buttons wide on a phone, the most it may take before the local hand drops under its floor at
  667x375; it stands the board's height and its narration takes the height its buttons leave, at least
  three lines on the supported phones (for which the round leaves its honba to the board and an incomplete
  replay's note folds into the round's toggle as a mark, at its end in place of the step, read out still), while a shorter window scrolls a narration it
  cannot hold, hinted at its foot. On a landscape window of at least 1024x600 the local hand is bounded by the board's width
  with height to spare, so a column there would shrink it before its text read well:
  the replay's controls run instead as one bar of a button's height under the board. Its round list
  lies over the board's right side, in the bar over its bottom-left above its toggle, as tall as its rounds, above a result's dimming; a replay that is
  not the whole game says so in the controls, and where it ends at its last stop, never over the board.
* **Visual gate:** `make visual-check` builds the app, checks the bundle budget, serves `dist/`
  with a replay fixture and a seat transcript over a mocked socket (no backend), and loads every
  storybook page (the board's worst case among them: every seat with four melds, long rivers, five
  dora, long names, AI marks and a pinned nameplate, and again with the most offers one discard can make,
  whose phone column ends before the right strip's second meld line; the strips' capacity: every opponent's
  full hand, fourteen faces with the drawn tile apart (with the most offers, and with a pressed riichi toggle
  beside a full bottom river) or thirteen backs, and legal mixed hands, each seat at one, two and three melds; a call at every seat; the dense round
  results; the
  decisions stories, the seating before the first deal, a turn in its bank, the live standings and the
  last result reopened from them among them; the board's
  standings over a hand-written short game; and the replay page's stories: its opening, autoplay
  running, another seat's view with the hands hidden, a result with them hidden, its round list,
  a double ron's result, the standings with a short and a long ledger, an incomplete replay, one ending
  on a round's result, a damaged one, loading and a replay not found), the replay and the live game, at
  its call prompt and at its turn, at 1280x800, 1440x900 and 1920x1080
  (Chromium), 1366x657 on the anchor, the worst board, a call beside the latest riichi discard's row, the
  full and mixed hands, the replay and the live turn alone (`onlyPages`: the band's corners shared, a chip
  bounded by its row), 800x600 on the anchor, the dense and two-step decisions, the worst board with and
  without offers and the full and a mixed hand (a narrow desktop's chrome), 1280x720, 1536x730 and 1440x770
  on the anchor, the offers and the full hands (`laptop-*`: either side of the short desktop's 760px),
  2560x1440 on the offers, the choices and the full hands (`desktop-large`: a control's height against the
  band), 680x375 and 700x375 (WebKit, `phone-680`/`phone-700`: wider phones at the floor's height, where the
  own tile reaches 36px) on the anchor, the switches, the strips' capacity and the replay, iPhone 13 portrait, the notch phone (the spec's capture model, 844x390 with insets of 47, 47
  and 21, asserted on every page) and the 667x375 floor (WebKit). The
  two engines run at once and each checks several pages at a time, each in its own context, which
  asks for reduced motion so each shot shows an animation's resting state. It
  fails on content that is hidden or empty (a decision control's tile previews aside, which a pair may
  shed), rivers within 3px of each other or the centre, a strip within
  6px of a river, an opponent's concealed hand tile off the river tile's width, a side hand's full reach (as its
  place reserves it, whatever the seat holds) over a play switch, the page's corner, a decision control or the
  timer, a badge name shortened in the middle on a page whose names are ordinary (`longNames` marks the
  pages whose names no badge holds), a badge of a decisions story off the place it holds on the others at that viewport, a
  play switch under 40x40, off the board or screen, within 4px of a tile, over a decision control or the timer, or
  whose knob's side or track's fill does not match its `aria-checked`, a
  decision's controls or timer off the place they hold while it is open once it is answered or expired
  (`CONTROL_FAMILIES`: the anchor's call), a landscape phone's toggle off its place once pressed (`TOGGLE_FAMILIES`:
  riichi in the band, a chi's and a kan's first step in the column), decision buttons over each other or the timer, a decision control
  within 4px of any tile outside the controls,
  a call over a decision control, the timer or the action source (the latest discard, an offered kan), tiles
  of different areas, a nameplate overlapping,
  anything outside the board or the screen, a call over the local hand's tiles, a status word, a plate's wind or
  marks or a name's end cut short, page overflow, board text under 10px, local hand tiles under
  32x42 on a landscape phone (a desktop's own tile has no separate floor) or, in landscape, no
  larger than every other tile on the board, and in landscape on another seat's face-up tile under 13x17, a
  notice over a tile, a plate, a decision button or the panel
  over the board, two names on a line of a result's scores under 12px apart, a decision
  button not wholly inside its container (never scrolled or clipped out of it), and decision, leave or replay buttons (its moves, its play and view switches, its round toggle, the round list's shown rows)
  under 40x40 or off the screen, or a round list off the board; on a desktop, on
  replay controls whose narration reads under 13px or past three lines,
  round and step under 13px or past two, or incompleteness under 12px; on a landscape phone, a
replay narration showing fewer than three lines at once or leaving its column. On the replay's route,
in both engines, a click, Enter and Space on Next must each step exactly once; the replay stories that
show a board run on the browser's clock for that reason, so their input keeps its real timing. On the anchor
checkpoints (the riichi toggle on and off), the worst board, a round result and the switches beside furiten, at the
spec's three viewports and the narrow desktop (`CONTRAST_VIEWPORTS`: the smallest faces at one device pixel to a CSS
pixel), every text, mark and face's glyph the page shows (a held-back face included) must keep 4.5:1 against what it is
painted on (`checkContrast`). The page is shot as drawn, without every text fill and glyph, without its pseudo-elements'
text, and without each batch of marks. A text (an element's own text nodes, or the text a pseudo-element draws, the
latter on the area its ink changed) is its painted colour (with every opacity above it) against the background the
page paints under its glyphs (found from shots painting all text one loud colour), in small square cells across its box
both ways, the worst kept, so no band or patch is outvoted;
its ink must also show. A glyph's every ink (its sprite symbol's fills and strokes, with their opacities; white
highlights aside: a paint the artwork authors white, `SPRITE_HIGHLIGHTS`, never a paint merely pale; the rendered
instance's and its ancestors' opacity folded in) is checked against the face's painted colour at every size, so a wrong colour fails on a small face
too; each ink must also be drawn, and its best pixel as drawn must reach the floor on a face of at least 24 device
pixels, under which a shortfall is reported in the page's summary line, never counted a pass (the spec: reported, not
redrawn). A mark (`CONTRAST_MARKS`, each piece of information its own mark, such as a stick's body apart from its dots
and a toggle's check apart from its box) is its best changed pixel against the same pixel without it; an absent mark
(an unpressed toggle's check) must change none. A target that cannot be read (under a filter, a symbol with no ink) or
shows no ink fails, listed. The summary line gives each kind's count and lowest ratio. A toggle's lamp must also show
its check exactly while the toggle is pressed, structurally. The table's surface runs on under the insets but never
under an aside (its box must not meet the aside's), and the board's content-overflow measure leaves it out.
On the decisions
story with every switch on beside furiten, Shift+Tab from the hand's first tile must reach a switch, and Space and
Enter on Auto win must each turn it once, sending nothing. It also fails on a round end that does not scroll inside its panel where it does not fit (its content
  past its foot at the scroll's end, its primary button and countdown wholly in view at both ends; a case
  forces a live result's panel short to prove it), a winner pager that does not page, any other panel that
  does not fit, a panel over a landscape board covering the
  page's corner, an aside that
  hides its controls, a rotate panel missing on an upright phone or shown elsewhere, and any console
  error, failed request or missing element, on a tile sprite that never loaded or a face whose
  symbol it lacks, and on a page whose face (Build) did not load: its FontFace `loaded` and
  `document.fonts.check`, which alone is also true of a family nothing declares. Every request off the page's
  origin is answered empty, so the app's own face is the only one a capture draws; one case
  (`font-blocked-anchor-turn`, at desktop-1440 and the 667x375 floor) refuses its request instead, and must show
  the face failed and pass every other check in the fallback stack. The standings must keep their rounds scrolling
  inside their sheet, never sideways in landscape,
  with the totals in view at its foot, no text under 10px, each round's and result's gain or loss in its
  tone's colour, and on a landscape phone their ways on
  and the rounds shown on the screen and at least 40x40. It writes a screenshot per page to
  `thoughts/screenshots/visual-check/`. `make install-frontend` installs its Chromium and WebKit
  (`npx playwright install`, matching the pinned `playwright`); on a fresh Linux host their system
  libraries come from `npx playwright install-deps`, which needs root. A board state worth checking
  at phone size is a storybook state and a case there; one the generated scenarios reach is a
  decisions story rather than a hand-written one. On success `make visual-check` stamps a
  fingerprint of its inputs (every non-ignored file under `frontend/game_v2`, tracked or not, and the
  `Makefile`) in `node_modules/.cache/visual-check.pass`; `make run-all-checks` skips the gate only
  when the current fingerprint matches that stamp, so a skip always means these exact inputs passed.
  Run directly, it always runs. While iterating, `node scripts/visual-check.ts --page <name>
  --viewport <name> --shots <dir>` (after `vite build`; each repeatable, matching names by substring)
  checks and shoots only those pages; it skips the replay load budget and never stamps.
* **Budgets**, in the same run: `scripts/bundle-budget.ts` reads the manifest the gate's build alone
  writes (`vite build --manifest`; it deletes it, so `dist/` never serves one) and fails when a
  route loads more JavaScript or CSS than its budget, raw or gzipped (the game route is the entry
  and its static imports; a lazy route is what it adds; the tile sprite and the font have their own, and the
  cold start, the entry with both, is reported; the standings' chunk, which no route imports statically, has its
  own), the budgets set about a tenth over the measured sizes, a lazy route's CSS at least 1 KiB
  over. Then the replay load budget loads the
  largest engine replay fixture on the same server and Chromium, slowed sixfold
  (`Emulation.setCPUThrottlingRate`), and fails when the median of a few reads of the replay view's
  `replay-load` measure (parse, reduce into the client timeline, steps and navigation index, before
  the first render) exceeds its budget. A run counts only when its measure's detail shows it read
  the whole fixture (its stops, rounds, final standings, the game's end and no damaged line) in a
  finite time.
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
  Lint enforces the layering in `src`: `.oxlintrc.json` has one `no-restricted-imports` override per layer and
  slice, banning upward imports (the entry and the router included), any slice's internals but its own, and the
  tests. The tests are exempt from the slice and public-entry bans. A new slice needs its own override, or its
  self-imports fail. An override replaces the rule's options, so each one repeats the zod paths and the tests ban.
* `shared/` — protocol, handoff storage, the socket adapter, the replay fetch, the clock, config and
  small helpers; imports nothing above it.
* `fixtures/` — generated data (the seat transcripts and the replay files) and a loader that hands
  the transcripts over unparsed for the tests; it imports nothing, and only storybook views and
  tests import it.

## Conventions

* lit-html templates, not React: components are functions returning a `TemplateResult`.
* Styles: Pico CSS v2 (`styles/_pico.scss`) styles semantic HTML; add classes only for
  project-specific components. The page is always dark (`index.html`), so `_pico.scss` assembles
  Pico's modules itself with only the dark scheme; a page using an element of a module it leaves
  out (a table, a dialog, a form control) enables that module there. Every colour is a `--ronin-*` token of
  `styles/_theme.scss`, the look spec's treatment A palette, never a literal in a component (a `color-mix` of tokens
  is fine); a new surface or mark takes an existing token or adds one there. The theme also sets Pico's own: its
  primary is the accent, so a plain button is the accent (the player's own action, the spec's one accent) and a
  `secondary` one the quiet outlined control. A tile's material is `styles/_tile.scss`'s alone: an ivory face with a
  rim (`--tile-ring`), an edge and a shadow (`--tile-lift`) cast toward the screen's bottom whatever the tile's turn
  (each turned frame sets `--frame-turn`, a sideways tile adds its quarter turn), all box shadows, so the material
  never moves a box; a back is the same box in one quiet colour, drawn by the stylesheet alone. Text has one face, `--ronin-font` (the face, Build),
  and no monospace: only the debug views (the `?debug` log, the storybook's sent messages) use `--ronin-font-debug`,
  which Pico's code elements take too. A figure that aligns (a score, a count, a timer, a result or standings figure)
  takes `type.figures` (`styles/_type.scss`) on its own numeric element, never on a container holding text: tabular
  digits, and `text-rendering: geometricprecision`, which stops headless Chromium snapping each digit's advance to a
  whole pixel. `styles/game-app.scss` is the one entry stylesheet; board layout lives in `styles/game-board/`.
* Named exports only in `src/` (tool configs such as `vite.config.ts` keep their default export).
* No `console.log` in application code.
* Lint and format follow the lobby's config (keep them in sync), but `new-cap`'s exceptions are this app's own:
  its capitalized lit-html components, each added as it is written. The `.oxlintrc.json` overrides
  relax only rules the restored code trips where it is shaped by its domain: the socket's
  replaceable `on*` handlers, the nested Zod tuples of the wire schemas and the long event
  dispatchers.
* Zod is `zod/mini` (lint bans classic Zod's specifiers in `src`, storybook views included: it does not
  tree-shake), with the English messages classic loads by default; the tests load `zod-setup.ts` too, so
  they read the app's messages. zod/mini's objects have no JIT, so `jitless` (`zod-setup.ts`) only guards
  against a classic schema slipping in, whose JIT's `new Function()` the game pages' CSP blocks.
  `zod-setup.ts` stays the first import of `index.ts`, ahead of any module that builds a schema.

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
hand-written branch on a generated scenario (`tests/fixtures/seat-transcripts.ts`): the client's own intents and
ticks (a kuikae or riichi discard it refuses, an expired prompt, a play switch turned on, `switchedOnBefore`),
a switch's send (the send the transcript recorded for the player's answer moved onto the message whose wait the
switch answers, the press after it then sending nothing, `answeredBySwitch`; written by hand with `expecting` where
the transcript recorded another answer), an answer racing a newer wait or the endpoint's rate
limit (the harness skips the endpoint, and a transcript keeps the server's order), and a payload
edited to a shape the server never sends.

The replay files under `src/fixtures/replays/` are generated, never edited by hand (they sit in
`src/` because the replay storybook opens a few, each imported by name in a chunk loaded with its story):
`make generate-replay-fixtures` records each from a game the engine plays
(`backend/scripts/replay_fixtures/`), and the checks fail when one drifts from what the engine
records now. A new replay case is a new scenario there. Tests load them through the fixtures'
loader, which reads them into the dispatcher's timeline as the replay view does, and the model's
tests assert outcomes on them, not only that they run: literals for what the model computes, and a
field the model passes through compared with the event it came from. Each is also projected per
seat, as that seat's socket would receive it (another seat's draw as its notice), to check that
after every line the seat's view keeps every hand size, its own tiles, the wall and the turn the
replay shows.

The `describe` block names the subject (the module or function under test) and the `it` title says
what it pins; tests carry no doc comments, and source files carry no file-header comment.
