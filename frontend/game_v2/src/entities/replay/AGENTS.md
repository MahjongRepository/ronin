# Replay entity

Moving through a recorded game: navigation, stops, cursor, address, autoplay, reader settings, controls.

- Every stop is a client timeline state; none is a table patched outside the dispatcher. Controls, round list,
  address, ledger and autoplay all move through the cursor functions over `buildNavigationIndex`.
- A stop is a move; bookkeeping (a deal's first draw, a new dora, an accepted riichi) belongs to the move before it,
  and annotations (game start, seat control lines) are never a stop (`buildActionSteps`). The replay opens on the
  first deal; `readReplay` refuses one without a deal.
- A result stop has a page per winner; stepping back into it lands on its last page.
- The address (`docs/architecture.md`, Replays) never names a result page; reader settings (hidden hands) never go
  in the address.
- Continuous moves (autoplay, held button, wheel) pause on every result page and at the last stop (`isPauseStop`).
- A replay that stops short of the game's end, or was cut at a damaged line, says so on every stop.
