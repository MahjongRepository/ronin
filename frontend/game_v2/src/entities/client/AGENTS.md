# Client entity

The dispatcher, its state, what the seat owes, desync recovery, play switches, timelines, seat scenarios and the live
board. The dispatcher's shape is in `frontend/game_v2/AGENTS.md`.

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
- **After riichi**, a fresh draw with no offers discards automatically, regardless of the play switches. A kan or
  win offer stays answerable by the player (Auto win can still claim a win). `automaticStep` uses the same unseen-wait
  guard as the switches, so a duplicate, reconnect or refusal never causes a repeated automatic answer. The locked
  hand keeps its normal appearance; only kuikae and picking the declaration discard grey out restricted tiles.
- **Play switches** answer only decisions on a wait id above `highestOpenedWaitId`, so a decision already open when a
  switch turns on, one re-sent after reconnect, or one a refusal reopened is the player's. The mark is never lowered,
  never taken from a snapshot's `wi`, and forgotten only on another game's table. `switchAnswer` is the policy. A
  deal, or a snapshot that left the hand (`snapshotLeftHand`), turns all switches off; a snapshot of the same hand,
  its result pending included, keeps them.

## Desync

- A protocol failure (unparseable message, undecodable frame, a `DesyncError` from the table or decision, or a
  fallback that would have to guess) puts the client out of step. Any other throw is a bug and reaches the driver.
  Never add a silent fallback that guesses.
- Out of step the client owes and answers nothing, never resends, and lets only the snapshot, the game's end and the
  game's last round end reach the table. Only a snapshot puts it back in step.
- The resync request's state is one field (`ResyncRequest`), one variant per state. Requests are counted per page,
  never reset; past `MAX_RESYNC_REQUESTS`, or on a snapshot it cannot take, the page ends as failed. A request
  refused because the game has not dealt waits for the first deal, so a long start pause spends no requests.
- A snapshot or re-sent opening naming the wait of a submitted decision leaves it submitted: a wait is never answered
  twice.
- **Silence watchdog:** `GameSocket` reports a server silent past `serverSilenceLimitMs` as a close, measured on the
  page's steady clock. The limit derives from the game's own timer settings; it copies none of the backend's pacing.

## Calls and the live board

- A primary click or tap on the board's background never answers a decision or confirms or dismisses a round result.
- Live shortcuts come from `playShortcuts` through the same intent gate as visible controls. One gesture closes only
  the topmost UI, backs out of a selection, or answers one decision; a result always needs its explicit control.
  `playInput` owns the board's DOM listeners and cancels a press across an input scope change or disposal. Repeated
  activation keys never answer again; arrow navigation only moves focus among playable tiles. The right-click
  preference is independent of replay controls and lives in browser storage through the live driver's dependencies.
- A local declaration shows its callout and plays its voice as soon as its intent is accepted, without changing the
  table. The submitted decision identifies its server echo even after the callout expires, so confirmation never
  repeats the voice or a lone callout. Other seats' calls still announce normally; a multi-ron result shows all
  winners. A kan's declaration and completion announce it only once. Calls end on a deal or a snapshot that left
  the hand, never on a move that calls nothing or the game's end. The yakuman gong waits for the server's result.
- `playDisplay` maps the whole client state for the live board and never restates what may be played: every tile
  intent and button is one the intent gate takes. `PlayBoard` only renders it; its view state is `PlayUi`, whose
  per-decision parts are keyed by wait id so a newer decision never inherits them. `PlayUi` moves only through
  `stepPlayUi`, which every driver calls after each step (a command, an intent once stepped, the client stepping on
  its own, the tile sprite) and never from a draw, so a render is a function of (state, ui) alone.
- Focus moves by the `data-focus-key` a component renders from its command or state, a control holding its own key
  and any group's (`focusKeys`), found under the board's own root (`focusByKey`, the sheet's focus back), never by
  reading classes or ARIA back from the DOM.
- The panel over the board is `PlayDisplay.overlay`, chosen by the mapper in one precedence (an end, the leave
  question, the notices' sheet, then the table's own panel from `tablePanel`) with whether it blocks the board; the
  replay's `replayDisplay` maps its own. Components only render the panel they are given; where it stands is
  GameBoard's (the free box `boardGeometry` reserves), never a page's.
- The settings menu's own transitions (the cog's toggle, a close, the sound switch) are `stepSettingsMenu`, which live's
  `stepPlayUi` and the replay's `stepReplayPage` share; each closes the menu on its own other input.
- Sounds are never `ClientEffect`s: `soundCues(before, after)` reads them off two consecutive states (a new showing
  of calls, one more discard, entry into a decision's time bank, a new second of a long decision's last five, an unseen
  call or win decision still open for the player), so scenarios and timelines stay silent
  and a snapshot plays nothing. The bank-entry cue only plays across the same open wait's base-to-bank transition,
  never on a reconnect already in the bank, and coinciding countdown cues play once. Only the live driver plays them,
  while `PlayUi.soundOn`. A move's part (`moveSoundCues`) is the replay's too.
- The board's script measurements are the table slice's: its geometry directive (`sizeBoard`) and the notices' clamp
  (`entities/table/ui/notice-clamp.ts`), which writes attributes only.
- Live regions announce each notice and call once, never each second or redraw; never `role="status"` (atomic).
  Every `GameBoard` keeps the calls' region; a showing's `announced` decides whether it is read (always on live, per
  move in a replay).

## Scenarios

`runSeatScenario` and `seatScenarioFromTranscript` take expected effects only from the transcript and the contract,
never from the client logic under test, so an early, late or missing automatic send is a mismatch.
