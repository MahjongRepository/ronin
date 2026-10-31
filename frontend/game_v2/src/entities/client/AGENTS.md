# Client entity

The dispatcher over client events, its state, the decisions and round confirm the seat owes, the loss of step, the
play switches, timelines and seat scenarios, and the live board and rotate panel drawn from that state. The app's
`AGENTS.md` (App) holds the dispatcher's and the state's shape; this file holds the rules of what the seat owes and
how the client recovers.

## What the seat owes

- **Decisions.** A decision opens only from a message carrying a wait id to the viewer's seat (its draw, its `turn`
  event, its call prompt), with the offers the server listed and nothing the client judged but the discard rule
  (kuikae, riichi's drawn tile). Its deadline is the client's estimate of the server's timer, in logical time from the
  timer settings and the bank the opening message names (none when it names no bank), backdated by a re-sent wait's
  elapsed time, so a countdown reads from `now`, never the wall clock. A turn also keeps when its base time runs out
  (the elapsed time comes off the base first), so its countdown shows the base and the bank apart, then the bank
  alone, marked and announced, as the server drains it; a reconnect's re-sent wait resumes both where the server
  stands, never a fresh full turn. Past it the decision shows as expired, for display only: the server alone decides
  by the wait id whether an answer counts, so an expired decision still takes one answer, and the client never
  answers without the player's instruction, standing (a play switch) or given (a press).
- **Answering.** Answering sends the action with the decision's wait id once and marks it submitted with the intent
  it took, which the display reads for the tile played and the control that answered, never the wire message. The
  server's next move closes it: every message type says whether it closes the decision or keeps it
  (`DECISION_AFTER`, exhaustive, so a new message type must say). A refusal while its wait goes on (a game error but a
  stale one, or the socket's rate limit) reopens it, and a session that holds no seat drops it (One client state),
  since the admission re-sends a wait the server still owes the seat. A refusal counts only when it names the
  decision's wait id (`refusalOf`): the rate limit can answer an older frame after the game moved on, so one naming no
  wait or another wait reopens nothing and shows no notice.
- **What may be played** is the intent gate's (`model/intents.ts`): `takesIntent` is the one test, the decision's
  answer on a socket it can send on, so the board offers exactly what stepping the intent would send. An answered
  decision keeps the controls it was answered from, judged by what the decision offers whatever its status
  (`offersIntent`), never by a forged open copy, so nothing moves while the server answers.
- **Play switches** (`model/play-switches.ts`): Auto win, No calls and Auto discard are the player's standing answers,
  a field of the client state. Turning one (the `toggle_switch` intent, taken only on a live seat while a round
  plays) sends nothing; the dispatcher answers for it where a message opens a decision on a wait id above the highest
  one a decision of the game opened before (`highestOpenedWaitId`), since the server raises the id only when a call
  ends a wait (a partial prompt response and a refusal keep it), stepping the switch's intent exactly as the player's
  press would be stepped: the same send with the decision's wait id, once, marked submitted with the switch that sent
  it (`bySwitch`). So the decision already open when a switch is turned on, a wait the client saw before, re-sent after
  a reconnect, and a decision a refusal reopened are never answered by a switch. The mark rises with every opened
  decision, the switches on or off, and is never lowered; it is kept across a drop (which drops the decision itself),
  a refusal and a deal, forgotten only on a table of another game, and never taken from a snapshot's `wi`: a wait the
  server opened while the socket was down is new to the client, and a switch answers it when the reconnect sends it.
  A wait the client sees before the server admits the seat raises it too, though the seat does not owe that wait, so
  the wait re-sent after the admission opens for the player's own answer, never a switch's. `switchAnswer` is the
  policy (the spec's Play switches): a win first (a turn's tsumo, a prompt's ron), then No calls' pass of a prompt
  offering a call and no ron, then Auto discard's discard of the drawn tile on a turn offering nothing else
  (`TurnDecision.drawnTileId`, null on the turn after the seat's chi or pon); no timer, since ron is taken at once.
- A deal turns all three switches off, as does a reconnect's snapshot that leaves the hand (`snapshotLeftHand`): one
  of another game or another deal number `n`, or where the table before it or the snapshot is not in a round. A
  snapshot of the hand's own result pending keeps the hand's `n`, so only its phase tells it left the hand. A snapshot
  of the same hand keeps them, and a reload starts with them off. A decision No calls passed shows no controls; one
  Auto win or Auto discard answered shows as answered. The board shows them (`PlayDisplay.switches`) only while the
  dispatcher takes their intent, never on a replay board.
- **Round confirm.** A round end's wait, or a reconnect's snapshot of a round advance that says the seat still owes
  it, opens the round confirm like a decision: one confirm intent sends it once with that wait id, then the seat waits
  for the others. Only the next deal (the last confirm's or the timeout's) closes it, and only a refusal naming its
  wait id reopens a sent one, as it does a decision; a late refusal of an earlier move names that move's wait, and the
  confirm's own stale reply follows the deal that closed it. A session that holds no seat drops it, since the
  snapshot says again whether it is owed. Its deadline is one per round, armed at the round end: the round advance
  timeout times the result's pages (the server's `results_shown`, a double ron's winners), backdated by the snapshot's
  elapsed time, and none when the snapshot names none: never a fresh full timeout. It is display only, shown labelled
  and kept while the seat waits: the client never confirms on its own and arms no timer for it. A double ron's pages
  each show Next until the last, which alone confirms, so the player has seen every winner before confirming.
- The game's last round end carries no wait and its game end follows at once: the table keeps that result and the
  live board shows it over the standings until the player dismisses it, which sends nothing; the standings' Last hand
  (the `show_last_result` intent) reopens it, on its first page, sending nothing either.

## Desync

- A protocol failure (`model/desync.ts`) puts the live client out of step with the server: a server message that does
  not parse, a frame the socket could not decode (`frame_undecodable`, apart from the browser's socket error,
  `transport_error`, which only its close follows), or a message its table or decision cannot take, which they report
  by throwing a `DesyncError` (`entities/table`); a silent fallback that guesses (an offer dropped for want of its
  tile, an added kan drawn as a closed one for want of its pon) is one too, and an offer of an unknown code or shape
  never parses, so no turn opens offering less than the server's for a switch to answer. An error that is not a
  `DesyncError` is a bug and propagates to the driver.
- Out of step, the client owes and answers nothing (its sync has no room for a decision or a round confirm), never
  resends what it sent, and keeps `highestOpenedWaitId`, so a wait re-sent after the snapshot is the player's to
  answer. The session still takes every message, but only the snapshot, the game's end and the round end before it
  (the game's last, which carries no wait) reach the table, every other message dropped. Those two carry the scores
  and the result the server settled, so a game that ends out of step ends on them, but the table records the loss of
  step (`lost_step`), dropping any result it kept, so only a result taken in step or that last round end opens the
  final result, its panel noting what may be wrong, and the standings mark their ledger incomplete
  (`entities/table/AGENTS.md`); a last round end it cannot take is one more message dropped. A game's end its in-step
  table refuses (the round end before it missed) is the first sign of the loss of step: the client goes out of step
  and takes that end once more, so the game still ends on the server's standings.
- Where the resync request stands is one field of the desync record (`ResyncRequest`), one variant per state with
  only its own due time, so no combination of flags implies one. It sends one resync request on the open socket and
  again only once one goes unanswered for `RESYNC_ANSWER_MS`. A
  request refused because the game has not dealt yet is answered: the client asks again when the first deal is due
  (`firstDealDue`), or, with no deal time ahead (a joined seat waiting for the game's players), only on the server's
  next game message, which a game start answers with the deal's time (its timer settings kept, so the
  silence limit covers the pause) and any other with a request at once, so a long start pause spends no requests. A
  dropped socket forgets the request and that wait, since the reconnect's own snapshot rebuilds it, so a refusal on
  the next socket is never taken for the old request's. While the reopened socket identifies, that snapshot is the answer awaited: the client asks on
  the same socket (which a RECONNECT the server took binds) only once it goes unanswered for `RESYNC_ANSWER_MS`, as
  when its frame did not decode, and never while a session retry waits (the socket then holds no seat; the resent
  identity's snapshot gets its own wait), so out of step and identifying always has a deadline, and the session
  admits it by the snapshot that answers, never by other traffic (`not_in_game` in answer means the socket holds no
  seat: `entities/session/AGENTS.md`).
- A snapshot puts the client back in step before it is taken, so what it says the seat owes is owed in step, and
  alone resets the board's count of failures (`unreadMessages`, the desync record's). A second snapshot that answers a
  request sent again can follow the player's answer to the first one's wait: a snapshot or re-sent opening naming the
  wait of a submitted decision or a sent round confirm leaves it submitted, so the wait is never answered twice.
- The requests are counted for the page, never reset by a snapshot or the session's admission, so one past
  `MAX_RESYNC_REQUESTS` ends the page as failed, as does a snapshot that does not parse (an incomplete one does not
  parse: `shared/protocol/AGENTS.md`) or that it cannot take, the page ending out of step, never put back in step by
  what it refused. A server message or an undecodable frame that arrives while the session has no open socket (it
  recovers its handoff, connects, awaits a transport retry or ended) is dropped, as the session drops it.
- Any other handling of a session error than the session's is the client's: a rate limit while the client's own
  resync request is outstanding is that request's, asked again when its answer comes due, and never reaches the
  session, which would resend its identity on a socket that may hold the seat.
- **Silence watchdog.** The client sends nothing on its own, so a socket whose peer vanished never fires `onclose`
  (one that never opens is the session's connect deadline instead). `GameSocket`, the socket's thin IO adapter (one
  connection attempt per instance; it never reconnects), therefore reports a server silent longer than its limit as a
  close, measured on the wall clock so the first check after a device wake sees the whole gap. The limit is the
  client's policy (`serverSilenceLimitMs`), which the driver keeps on its socket: the longest wait the game's timer
  settings allow (a turn's base and full bank, a call window, a result's advance over a double ron's pages, the start
  pause) plus a margin for late timers, never under the default (`DEFAULT_SERVER_SILENCE_LIMIT_MS`, hand-derived from
  the session `TimerConfig` defaults, `backend/game/session/AGENTS.md`, Pacing), which also holds before the settings
  arrive; re-derive the default when the default pacing changes.

## Calls and the game start

- Before the first deal the board's panel is the seating (`gameStartDisplay`): the game's length and first round,
  each seat's wind and player, the dealer, AI players and the viewer marked, and the server's game start pause counted
  down (`firstDealCountdown`, from the game start's timer settings), or only "Starting…" where none is known or it
  ran out.
- A call (chi, pon, kan of any kind, a riichi declaration's discard, ron, tsumo, a triple ron's three rons) shows by
  its seat for a moment, from the dispatcher's state (`calls`, `model/calls.ts`): a table event's calls
  (`eventCalls`) replace the ones shown. A kan is called once, when the table first shows it: neither the meld that
  completes a kan its chankan prompt showed nor the prompt a reconnect re-sends calls it again, however long the
  prompt waited, while another kan of the same seat is called afresh. A live message's last `CALLOUT_MS`
  (`entities/table`, which the board hands its stylesheet as `--callout-ms`) or until a newer call, never ended by a
  move that calls nothing, since one may follow at once (an AI player's discard after its pon, the viewer's draw
  after a riichi), nor by the game's end, so the last win shows its call; a deal, or a reconnect's snapshot that
  leaves the hand (`snapshotLeftHand`), ends them, since it starts a new board however soon it follows the hand's last
  call (a snapshot of the same hand keeps them), and a failed or left session drops them. A replay line's last until
  the next move, so each stop shows its own move's calls and stepping or autoplay leaves none behind.
- Each call lies over its caller's river at the first of a few fixed spots (in river tiles and rows,
  `CALLOUT_SPOTS`) clear of the latest discard's row (top, bottom) or column pair (sides), its chip no taller than a
  river row (its font bounded by the row, its pop never past full size), so it never covers the action source, a
  control or the own hand. The board keys each showing, so a new one replays its CSS animation and a redraw does not;
  it takes no input, and a win's call shows before the result panel, which waits for it by CSS alone; the board waits
  only when told its panel is a result (`overlayIsResult`), so the leave question and an end show, and take the
  focus, at once.
- The seat in turn is cued only by the centre's bar on its side and its badge's underline (the spec's turn cue), the
  viewer's turn and call prompt by nothing else; furiten shows only while a round plays, as a dot and the word in its
  slot by the hand (`GameBoard`'s `furiten`).

## The live board

- `playDisplay` maps a whole client state for the live board: the table from the viewer's seat with only its hand
  face up, each of its tiles marked by the open decision (selectable, declaring while the riichi toggle is on, held
  back, the one an answer played), the intent each selectable tile sends, the decision's controls ranked
  (`DecisionAction.rank`: the wins, ron, tsumo and kyuushu, first; then riichi as one toggle and one control per other
  kind of offer in the server's order; then a pass), the countdown, where the decision stands (open, expired,
  answered), what Escape does, furiten, a chankan offer's kan (`sourceMeld`), and the round result's controls (its
  one primary button, the result's pager only secondary beside it, the countdown, waiting for the others). What may be
  played is never restated there: every tile intent and button is one the intent gate takes.
- `PlayBoard` only renders that, with the table's panel over it, and routes a command: an intent goes to the
  dispatcher; the view state is `PlayUi`, an input of the mapper too: the riichi toggle and a call's choice of tiles,
  each keyed by the decision's wait id so a newer decision never inherits it, each turning the other off; the round
  result's page, keyed by the hand the result ends (the game and its deal number `n`, which a reconnect's snapshot of
  the result pending keeps), so a newer result opens on its first page while a reconnect keeps the page; the nameplate
  pinned for score differences; and the notices' sheet.
- A kind of offer with a choice of tiles (two chi, two kan) is one control that opens its second step, which is that
  control pressed, each choice the dispatcher takes as a tile group laid by `meldTiles` as the meld will lie, the
  pressed control after them (where the first step had it, so pressing it never moves it; a desktop row shows it
  first), and Back in Pass's place; Back, Escape (the board's) and the call pressed again go back, Escape moving a
  focus it finds on a decision control to the call's control, and Escape also turns the riichi toggle off. One Escape
  is one step: a pinned badge's unpinning first, and never an Escape a panel over the board already took (the leave
  question's). An answered decision keeps the controls it was answered from, inert, the one whose answer matches the
  sent message marked, and its steps no longer change.
- **The page's corner** (`GameMenu`): the way back and the session's status as a dot, with one short word
  (`SessionStatusDisplay.word`): the socket's state while the session runs, none while connected, and once it ended
  what happened (Ended, Replaced, Removed), none once the player left (a short board, too narrow for a word, shows the
  dot alone, never part of the word; an end that is no failure, the game's, the player's leaving or another tab's, in
  the quiet ended tone, never the error's), the player's whole wording in its title and read out, the notices saying
  more. `PlayBoard` draws it when given the status, the decisions storybook too. With `?debug` (any value but `0`,
  `false`, `no` or `off`) the corner adds the debug log, a collapsed sheet of every message, send and transport event
  under the machine's own status; without it the view keeps no log at all.
- **Notices** (`playDisplay`'s), stacked ongoing conditions first, then acknowledgements (`NoticeKind`'s order): a
  seat this page held and lost to a drop while it reconnects, or a connection failing since the page opened, each
  worded the same across its retries so it is announced once (a page that only resumes its seat, a reload, shows
  neither); short-lived ones held in the client state with a logical-time expiry (the seat back after a snapshot of
  such a drop, which a second drop replaces, and a refused move, shown only for the refusal that reopens the request
  it names); the protocol failures since the last snapshot (Desync), on the console too, shown until a snapshot
  rebuilds the table, which may be wrong until then; and tile faces that did not load, with a reload, until a retry
  loads them. An end that stops the session on the page blocks the board, and takes the rotate panel's place, with
  why and a way back.
- A notice is never wider than its place, and a stack taller than it is never cut (`entities/table/ui/notice-clamp.ts`):
  the tallest notices clamp to whole lines, then, where even one line each does not fit, the last notices are left
  out; a clamped notice ends in "Show all" on a line of its own (the whole notice its target, at least 40px high; "+n"
  where it stands for notices left out), its way out (Reload) moving to the sheet. A text's overflow is the one thing
  CSS cannot tell, so the clamp is the board's one script measure: a directive on the place reads each text's whole
  height (a clamped text's scroll height, so it never undoes a clamp to measure) after each render, as the board's box
  changes (in the next frame, so a write never loops the observer, watching the board once the render put the place in
  it) and once the face loads, and writes only attributes, the lines and "Show all"'s name (its "+n" included).
- "Show all" opens the notices' sheet (`PlayUi.noticeSheet`, the opener's kind): every notice whole with its way out,
  that play goes on with the decision's or round confirm's seconds (`pendingCountdown`, its thresholds announced as the
  rotate panel's), over the board as a panel, the board inert, Close focused, Tab kept inside, Escape (handled, so no
  one else takes it) or Close closing it; it ranks under an end and the leave question (`PlayOverlay`) and over the
  table's panel, which returns as it closes, and it stays open while any notice shows, closing for good once none does
  (`settledPlayUi`, which the view runs on each draw). However it closes, once every other focus has settled, a focus
  that fell to the page's body goes back to the board (`focusBackOnClose`): the opener's "Show all" while a player can
  reach it, else another, the panel it gave way to, the decision's controls, the hand, else the board itself (made
  focusable then, never in the Tab order); a focus an end or the leave question took stays.
- The notices are read by a polite live region of their own outside the inert layout, not atomic and relevant to
  additions alone (never `role="status"`, which is atomic), one line per notice keyed by its words, so a new notice is
  read alone, once, and a clamp, a redraw or a notice leaving never; the live board's calls likewise (`announceCalls`,
  each showing once by its callers' names, the drawn chips `aria-hidden`).
- **The rotate panel** (the app's Phone policy) shows the session's status in a player's terms, a way back to the
  lobby and, while a decision or a round result's confirm awaits the viewer, that play and its countdown go on, with
  the seconds left. Only the status line and the countdown's thresholds (10 s, 5 s, expiry) are live regions, never
  each second. The countdown reads the deadline against the state's `now`, never the wall clock; the driver also wakes
  at each change of the shown second (`nextCountdownChange`) so `now` moves.

## Scenarios

- A `SeatScenario` is one seat's scripted run as plain data: the lobby handoff, then ordered client events, each step
  naming exactly the effects it must describe (none when omitted), so every send is asserted and never fed in.
  `runSeatScenario` builds its timeline and reports every step whose effects part from the scenario, a payload that
  does not parse included.
- `seatScenarioFromTranscript` builds one from a seat transcript the backend generated (what the server sent one seat
  and what the seat sent it, JOIN_GAME and RECONNECT included with the ticket left out, and the closes it saw, parsed
  strictly with Zod where it arrives as JSON). It drives the client as the live driver does, ticking at each deadline
  the client holds before the next recorded event, but takes the effects it expects only from the transcript and the
  contract, never from the client logic under test: each recorded send at its recorded time (an answer or a round
  confirm as the intent choosing it, a send the client makes on its own, a resent identity, as a tick then, the
  identity after an open as that open's effect), a reopened socket asked for at its recorded open, the handoff
  forgotten after a close the contract makes terminal (its own copy of the codes) and after the game's end, and
  nothing from any other tick, so an automatic send that is early, late or missing is a mismatch. Because sent
  messages parse strictly, an expected send also pins the builders' wire shape to what the server accepted. The tests
  run the generated ones; nothing in the app runs one yet.
