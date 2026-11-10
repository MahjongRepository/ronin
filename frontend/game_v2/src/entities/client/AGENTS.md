# Client entity

The dispatcher, its state, what the seat owes, desync recovery, play switches, timelines, seat scenarios and the live
board. The dispatcher's shape is in `frontend/game_v2/AGENTS.md`.

Live and replay dispatch live in separate modules so the live entry never imports replay parsing. Both use the same
table transition and call model; replay dispatch loads with the replay route.

## What the seat owes

- The seat owes at most one thing: a decision or a round confirm, never both. It owes only while its session holds
  the seat; otherwise every step drops it (`settledPending`), since the server re-sends every wait it still owes after
  admission.
- A decision opens only from a message with a wait id for the viewer's seat, while a round plays; an opening anywhere
  else is a `DesyncError`. It offers exactly what the server listed; the client judges only the discard rule
  (kuikae, riichi's drawn tile). The intent gate (`takesIntent`) is the one test of what may be played, so the board
  offers exactly what stepping the intent would send. Once answered, its controls and timer disappear;
  the internal submitted state still prevents a second answer.
- After the viewer's pon or chi, the play decision opens on the server's `turn`, never on the meld. A reconnect
  snapshot opens no play decision: the server re-sends its opening message. It may restore an owed round confirm.
- Deadlines are display only: the client estimates the server's timer in logical time (re-sent waits backdated by
  their elapsed time) and never answers, confirms or arms a timer on expiry. An expired decision still takes one
  answer; the server decides by wait id whether it counts. Turns and calls use the same base-plus-bank
  countdown, reading the bank from each opening message rather than carrying a client-side reserve.
- An answer is sent once and marked submitted. `DECISION_AFTER` says, for every message type, whether it closes or
  keeps the decision; a new message type must be added. A refusal reopens only when it names the decision's wait id
  (`refusalOf`).
- A round confirm closes only on the next deal. Its deadline is the timeout the round end names, never a count of
  result pages. A double ron confirms only from its last page.
- The start confirm (Tenhou's NEXTREADY) is the same `RoundConfirm`, told apart by the table showing no round result
  (`startConfirmOf`): the first deal opens it for a seat the server awaits (its wait id and whole timeout), a snapshot
  of the first deal before its first draw restores it, owed, sent or in already, and the first draw closes it. Only
  the opening screen's OK sends it; the result's confirm never does.
- **Automatic discards**, after riichi or with Auto discard on, hold a fresh draw with no offers in the hand for
  one second. Riichi discards happen regardless of the play switches; otherwise turning Auto discard off cancels
  the pending discard. The wait-bound deadline uses the dispatcher clock and is cancelled when the
  decision is answered or lost, including on disconnect or desync. A kan or
  win offer stays answerable by the player (Auto win can still claim a win). `automaticStep` uses the same unseen-wait
  guard as the switches, so a duplicate, reconnect or refusal never causes a repeated automatic answer. The locked
  hand keeps its normal appearance; only kuikae and picking the declaration discard grey out restricted tiles.
- **Play switches** answer only decisions on a wait id above `highestOpenedWaitId`, so a decision already open when a
  switch turns on, one re-sent after reconnect, or one a refusal reopened is the player's. The mark is never lowered,
  never taken from a snapshot's `wi`, and forgotten only on another game's table. `switchAnswer` is the policy. A
  deal, or a snapshot that left the hand (`snapshotLeftHand`), turns all switches off, except Auto win while the
  settings menu keeps it between rounds (`LiveClient.keepAutoWin`, the driver storing it in this browser; turning it
  on turns Auto win on, turning it off leaves Auto win as it is); a snapshot of the same hand, its result pending
  included, keeps them.

## Desync

- A protocol failure (unparseable message, undecodable frame, a `DesyncError` from the table or decision, or a
  fallback that would have to guess) puts the client out of step. Any other throw is a bug and reaches the driver.
  Never add a silent fallback that guesses.
- Out of step the client owes and answers nothing, never resends, and lets only the snapshot, the game's end and the
  game's last round end reach the table. Only a snapshot puts it back in step.
- The resync request's state is one field (`ResyncRequest`), one variant per state. Requests are counted per page,
  never reset; past `MAX_RESYNC_REQUESTS`, or on a snapshot it cannot take, the page ends as failed. The server
  refuses a resync only while the pending game waits for its players, so a request refused as the game not started,
  or a JOIN_GAME socket's, waits for the next game message and then asks at once, identifying or not; a long wait for
  the players spends no requests.
- A snapshot or re-sent opening naming the wait of a submitted decision leaves it submitted: a wait is never answered
  twice.
- **Silence watchdog:** `GameSocket` reports a server silent past `serverSilenceLimitMs` as a close, measured on the
  page's steady clock. The limit derives from the game's own timer settings; it copies none of the backend's pacing.
- **Round trip:** `GameSocket` also pings the server, one ping in flight, and keeps the pongs from the dispatcher and
  the silence watchdog, since the endpoint answers them without the game;
  the median it reports is page IO in `PlayUi`, forgotten as a new socket opens, never client state. The mapper
  decides the cog's mark (`round-trip.ts`): a slow round trip marks it like a status word, below any word the status has.

## The opening screen

- The opening screen (`LiveClient.opening`) is the dispatcher's: unseen, showing, or closed, and a page shows it at
  most once, unless a start confirm comes owed after it closed. The game's first deal opens it (`start`), never the
  game start just before it, so its seating never grows its scores and OK once shown; so does a
  page's first snapshot of the first deal before its first draw; the first draw closes it, never a client deadline,
  since the server times the start confirm out. A page's first snapshot of any other round in play, when it never saw
  the game start, opens it (`resume`) for `OPENING_SCREEN_MS` (none over a result pending). A round's or the game's
  end closes either. A deal or snapshot under it changes only what its seating shows (`tableSeatingPanel`).
- The OK is the `confirm_opening` intent: the start confirm while the seat owes it, after which the OK stays in place,
  disabled, waiting for the others with the confirm's countdown running to 0; else (the resume screen, a seat the
  server does not await, a socket that dropped the confirm) a close that sends nothing, kept so the OK is still the
  gesture that unlocks the page's audio.
- It never speaks of sound. The page's audio unlocks inside its first user gesture (`index.ts`, `unlockOnGesture`
  around the Web Audio output's `unlock`), the OK's or any other, and no sound plays before the page's first
  activation.

## Calls and the live board

- A primary click or tap on the board's background never answers a decision or confirms or dismisses a round result.
- Live shortcuts come from `playShortcuts` through the same intent gate as visible controls. One gesture closes only
  the topmost UI, backs out of a selection, or answers one decision; a result always needs its explicit control, which takes the focus as it first shows so Enter or Space presses it. The
  one exception is a pointer's click on a playable tile with the settings menu open, which closes the menu and goes on
  to the tile (a mouse discards, a finger lifts); any other click outside the menu only closes it.
  Digit keys 1-9 press the decision controls the mapper numbers (`DecisionAction.digit`, shown as keycaps): at a first
  step all but the pass, at a call's second step only its choices of tiles, in the mapper's order, never a layout's
  (the desktop row moves the pressed call first). They read the physical key (`event.code`), the numpad only while it
  types digits, never under any panel or the open menu, and the same digit within `DIGIT_SETTLE_MS` of acting is dropped
  once the controls it presses changed, so a double tap never takes an unseen choice.
  Enter or Space outside a focused control presses the opening screen's OK (`confirm`), its only key; the board's own
  keys (Escape's and right-click's back, pass or drawn-tile discard, tile arrows) still reach a decision under it (`leavesBoardKeys`). `playInput` owns the board's DOM listeners and cancels a press across an input scope change or disposal. An Escape or a right-click within `SHORTCUT_SETTLE_MS` of the last of its kind that had a shortcut is dropped, so a double press never closes a panel and then discards, or answers a decision and then the one its answer opened. Repeated
  activation keys never answer again; arrow navigation (the arrows, or A and D by position) only moves focus among playable tiles, or every hand tile while none plays, wrapping round the
  hand. The right-click
  preference is independent of replay controls and lives in browser storage through the live driver's dependencies;
  turned off, a right-click does nothing, yet still never opens the browser's menu where it would have acted.
- A local declaration shows its callout and plays its voice as soon as its intent is accepted, without changing the
  table. The submitted decision identifies its server echo even after the callout expires, so confirmation never
  repeats the voice or a lone callout. Other seats' calls still announce normally; a multi-ron result shows all
  winners. A kan's declaration and completion announce it only once. Calls end on a deal or a snapshot that left
  the hand, never on a move that calls nothing or the game's end. The yakuman gong waits for the server's result.
  A win's context (`WIN_CALLOUT_CONTEXT_MS`) holds for a delayed result independently of the shorter
  visible callout. Once a result panel starts its opening delay, expiry of that context never truncates it.
- `playDisplay` maps the whole client state for the live board. `PlayBoard` only renders it; its view state is `PlayUi`, whose
  per-decision parts are keyed by wait id so a newer decision never inherits them. `PlayUi` moves only through
  `stepPlayUi`, which every driver calls after each step (a command, an intent once stepped, the client stepping on
  its own, the tile sprite) and never from a draw, so a render is a function of (state, ui) alone.
- Focus moves by the `data-focus-key` a component renders from its command or state, a control holding its own key
  and any group's (`focusKeys`), found under the board's own root (`focusByKey`, the sheet's focus back), never by
  reading classes or ARIA back from the DOM.
- The panel over the board is `PlayDisplay.overlay`, chosen by the mapper in one precedence (`PlayPanel`) with whether it blocks the board; the
  replay's `replayDisplay` maps its own. Components only render the panel they are given; where it stands is
  GameBoard's (the free box `boardGeometry` reserves), never a page's.
- The settings menu's own transitions (the cog's toggle, a close, the sound and animations switches) are `stepSettingsMenu`, which live's
  `stepPlayUi` and the replay's `stepReplayPage` share; each closes the menu on its own other input.
- Sounds are never `ClientEffect`s: `soundCues(before, after)` reads them off two consecutive states, so scenarios and timelines stay silent
  and a snapshot plays nothing. The bank-entry cue only plays across the same open wait's base-to-bank transition,
  never on a reconnect already in the bank, and coinciding countdown cues play once. Only the live driver plays them,
  while `PlayUi.soundOn`. A move's part (`moveSoundCues`) is the replay's too.
- The board's script measurements are the table slice's: its geometry directive (`sizeBoard`) and the notices' clamp
  (`entities/table/ui/notice-clamp.ts`), which writes attributes only, plus its presentation-only motion snapshots.
  The dispatcher advances the board's motion cue only when the table changes, marking reconnect snapshots and
  loss of step as resets. A countdown or UI redraw cannot restart a tile's animation.
- Live regions announce each notice and call once, never each second or redraw; never `role="status"` (atomic).
  Every `GameBoard` keeps the calls' region; a showing's `announced` decides whether it is read (always on live, per
  move in a replay).

## Scenarios

`runSeatScenario` and `seatScenarioFromTranscript` take expected effects only from the transcript and the contract,
never from the client logic under test, so an early, late or missing automatic send is a mismatch.
