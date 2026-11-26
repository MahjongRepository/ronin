# Replay entity

Moving through a recorded game: navigation, stops, cursor, address, autoplay, reader settings, the page's screen, controls.

- Every stop is a client timeline state; none is a table patched outside the dispatcher. Controls, round list,
  address and autoplay all move through the cursor functions over `buildNavigationIndex`.
- A replay whose address names no position opens on the seating of the table as the game started (`startTable`), until the reader starts or moves; that seating is never a stop.
  With the sound on, every replay opens on it, a linked one included, and the wheel never leaves it: a browser plays
  no sound before a click or key, which the wheel is not, so Start is that click.
- A stop is a move; bookkeeping (a deal's first draw, a new dora, an accepted riichi) belongs to the move before it,
  and annotations (game start, seat control lines) are never a stop (`buildActionSteps`).
- A turn move is the bottom seat's (`nextTurnCursor`, `prevTurnCursor`), so changing the viewpoint changes where it goes.
- The address (`docs/architecture.md`, Replays) never names a result page; reader settings (hidden hands, marked
  tsumogiri) never go in the address.
- Autoplay and a held button or key pause on every result page and at the last stop (`isPauseStop`); the wheel holds
  each result page (`WHEEL_RESULT_HOLD_MS`). An observed game's autoplay is the exception: it keeps the table's pace
  (`docs/architecture.md`, Game client contract, Observing; `observeAutoplayDueAt`, `observeHeldUntil`), crosses its
  results and waits only at the newest stop of a stream that has not ended; nothing the viewer does pauses it, the
  page hiding included.
- An observed game (the observe page) is the same replay read from the observe stream (`docs/architecture.md`, Game client contract, Observing), rebuilt
  as records arrive, keeping the view, the reader's settings and autoplay. Only that source may lack the seed. Before its
  first playable records it shows the live game's start screen from the answer (the game type, the players East to
  North, the time left in the OK's place); it then opens with autoplay on and no seating, at the first deal for a
  viewer who saw that countdown, else at the newest stop, and it never reads or writes the address. It plays as live
  play does: the `observe` motion cue (live play's `step`, an opponent's face-up draw held too) and held results, no move of the cursor taken from the viewer (keys, wheel, round
  list, result pages), its controls only the next seat's view in live play's band. A badge under the centre's wall
  count says it is live while the stream is, and once the server no longer holds the game it keeps the board and its
  status links the saved replay.
- Replay tile motion settles the previous stop before measuring the next, so rapid navigation never queues behind
  movement or carries old tile effects into the new stop. The replay cue (an archive's) omits the live discard pause; backward
  steps, jumps and round changes show their destination immediately.
- A replay that stops short of the game's end, or was cut at a damaged record, says so on every stop.
- The replay page's screen (loading, failed, an observed game's countdown or its gone notice, loaded) moves only
  through `stepReplayPage`: stamped input in, screen and requested IO (address write, settings save, focus, the
  observe stream's next request) out. It reads no DOM or clock and arms no timer; autoplay and a
  held button's repeat are deadlines in the screen (`replayPageDeadline`) that come back as ticks.
- The reader's own input closes the settings menu, as live's page controls do; what keeps it open is
  `KEEPS_SETTINGS` (`model/replay-page.ts`).
- A step on to the next stop (Next, autoplay, a held Next, the wheel) asks the view to play that move's sounds
  (`play_sounds`, from `moveSoundCues`) while the sound is on; a jump, a step back or a result's page plays none. The
  sound setting is the live game's (`save_sound`), never the reader's settings.
- Which moves announce the calls they show (`ShownReplayCall.announce`) is the spec's (`docs/game-client-look.md`,
  Notices); it is not `moveEffects`' step-on test, which a held Next and the wheel pass.
- The tools' menu is the spec's (`docs/game-client-look.md`, Replay): the hand copied (`copy_text`) or opened in
  Tenhou's analysis (`open_url`), and the reader's switches. It and the round list never stand open together, neither
  acts under the seating, the copy key leaves selected text to the browser, and the live game has neither.
- `ReplayBoard` assembles the replay's `GameBoard` (panel, controls, status, menu) from `replayDisplay` and the
  loaded screen, as `PlayBoard` does the live one; it decides nothing. Its controls fill the live board's slots; none places itself.
- What a page finds of the slice's UI by selector is exported beside the component that renders it (its `*_SELECTOR`
  and `*_ATTRIBUTE` constants); change both together.
