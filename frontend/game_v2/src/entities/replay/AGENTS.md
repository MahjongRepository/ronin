# Replay entity

Moving through a recorded game: navigation, stops, cursor, address, autoplay, reader settings, the page's screen, controls.

- Every stop is a client timeline state; none is a table patched outside the dispatcher. Controls, round list,
  address and autoplay all move through the cursor functions over `buildNavigationIndex`.
- A replay whose address names no position opens on the seating of the table as the game started (`startTable`, each seat
  at its first deal's score: the game's start names none), the board under it before its first deal, until the reader starts or moves; that seating is never a stop.
  With the sound on, every replay opens on it, a linked one included, and the wheel never leaves it: a browser plays
  no sound before a click or key, which the wheel is not, so Start is that click.
- A stop is a move; bookkeeping (a deal's first draw, a new dora, an accepted riichi) belongs to the move before it,
  and annotations (game start, seat control lines) are never a stop (`buildActionSteps`). The replay opens on the
  first deal; `readReplay` refuses one without a deal.
- A result stop has a page per winner; stepping back into it lands on its last page.
- The address (`docs/architecture.md`, Replays) never names a result page; reader settings (hidden hands) never go
  in the address.
- Autoplay and a held button or key pause on every result page and at the last stop (`isPauseStop`); the wheel holds
  each result page `WHEEL_RESULT_HOLD_MS` and steps on while it keeps turning.
- Replay tile motion settles the previous stop before measuring the next, so rapid navigation never queues behind
  movement or carries old tile effects into the new stop. The replay cue omits the live discard pause; backward
  steps, jumps and round changes show their destination immediately.
- A replay that stops short of the game's end, or was cut at a damaged record, says so on every stop.
- The replay page's screen (loading, failed, loaded) moves only through `stepReplayPage`: stamped input in, screen and
  requested IO (address write, settings save, focus) out. It reads no DOM or clock and arms no timer; autoplay and a
  held button's repeat are deadlines in the screen (`replayPageDeadline`) that come back as ticks.
- The reader's own input (a move, a key the page takes, Start, autoplay, the hands, the round list's toggle and close,
  a seat to view from, the wheel, a step button's press) closes the settings menu; its own commands, ticks, the page
  hiding and a click outside the round list leave it as it is.
- A step on to the next stop (Next, autoplay, a held Next, the wheel) asks the view to play that move's sounds
  (`play_sounds`, from `moveSoundCues`) while the sound is on; a jump, a step back or a result's page plays none. The
  sound setting is the live game's (`save_sound`), never the reader's settings.
- A move says whether the calls it shows are announced (`ShownReplayCall.announce`): a single step either way (Next or
  Prev, a key press, a press's first step) and autoplay do; a jump (a round, an end, the round list, an address), a
  held step's repeats (pointer or key) and the wheel show them silently. A showing carried over later moves keeps its
  flag. This is not `moveEffects`' step-on test, which a held Next and the wheel pass.
- `ReplayBoard` assembles the replay's `GameBoard` (panel, controls, status, menu) from `replayDisplay` and the
  loaded screen, as `PlayBoard` does the live one; it decides nothing. Its controls fill the live board's slots: the
  group (moves, options, the round list over them) the band end, the status the field; none places itself.
- What a page finds of the slice's UI by selector (`ROUND_LIST_SELECTOR`, `ROUND_LIST_TOGGLE_SELECTOR`,
  `STEP_BUTTON_ATTRIBUTE`) is exported beside the component that renders it; change both together.
