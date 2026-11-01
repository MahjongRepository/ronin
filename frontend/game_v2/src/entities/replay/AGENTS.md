# Replay entity

Moving through a recorded game: navigation, stops, cursor, address, autoplay, reader settings, the page's screen, controls.

- Every stop is a client timeline state; none is a table patched outside the dispatcher. Controls, round list,
  address and autoplay all move through the cursor functions over `buildNavigationIndex`.
- A replay whose address names no position opens on the seating of the table as the game started (`startTable`, each seat
  at its first deal's score: the game's start names none), the board under it before its first deal, until the reader starts or moves; that seating is never a stop.
- A stop is a move; bookkeeping (a deal's first draw, a new dora, an accepted riichi) belongs to the move before it,
  and annotations (game start, seat control lines) are never a stop (`buildActionSteps`). The replay opens on the
  first deal; `readReplay` refuses one without a deal.
- A result stop has a page per winner; stepping back into it lands on its last page.
- The address (`docs/architecture.md`, Replays) never names a result page; reader settings (hidden hands) never go
  in the address.
- Continuous moves (autoplay, held button, wheel) pause on every result page and at the last stop (`isPauseStop`).
- A replay that stops short of the game's end, or was cut at a damaged line, says so on every stop.
- The replay page's screen (loading, failed, loaded) moves only through `stepReplayPage`: stamped input in, screen and
  requested IO (address write, settings save, focus) out. It reads no DOM or clock and arms no timer; autoplay and a
  held button's repeat are deadlines in the screen (`replayPageDeadline`) that come back as ticks.
- What a page finds of the slice's UI by selector (`ROUND_LIST_SELECTOR`, `ROUND_LIST_TOGGLE_SELECTOR`,
  `STEP_BUTTON_ATTRIBUTE`) is exported beside the component that renders it; change both together.
