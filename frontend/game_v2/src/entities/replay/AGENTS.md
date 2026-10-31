# Replay entity

How a recorded game is moved through: its page-ready read, its stops and cursor, the address, autoplay, the reader's
settings, the narration and the replay's controls and round list, for the replay page (`src/views/AGENTS.md`) and its
storybook.

- It sits above the client: it may use `client`, `table` and `tile`, and nothing below imports it. The client's
  reader (`readReplayTimeline`) makes the timeline and knows no stop; `readReplay` here builds the navigation over
  that timeline's step events and tables, and refuses a replay with no deal, so a `LoadedReplay` always holds the
  first deal it opens on (`opening`). The board (`entities/table`'s `GameBoard`) draws the controls only as a slot it
  is handed, never importing them.
- A replay's cursor contract is pure functions over one navigation index (`buildNavigationIndex`), which the
  controls, the round list, the address, the ledger and autoplay all move through. A stop is a move: a deal (with its
  first draw), a draw, a discard (with the riichi its passing deposits, so the stick shows on the declaring discard),
  a call, a kan declared open to chankan, a round's result, the game's end. Bookkeeping (a deal's first draw, a new
  dora, an accepted riichi) belongs to the move before it; annotations (the game start, a seat control line) are
  never a stop. One rule places both (`buildActionSteps`): a move's stop runs through its last bookkeeping entry,
  past any annotation between, and an annotation after it shows from the next stop. So a seat that changes hands in a
  riichi's call window (the server records the line before the acceptance its AI player's pass brings) is told on the
  declaring discard, which shows the deposit, and otherwise a seat's change of hands is told and marked from the move
  after its line. Every stop is a timeline state; none is a table patched outside the dispatcher. The replay opens on
  the first deal: nothing before it is a stop. Stops are numbered within their round from 0 at its deal, the game's
  end the last round's last stop, and a round's result (`roundResultCursor`, where the standings' rows go) the stop
  whose table shows it ended. A result stop has a page per winner; stepping pages through them, and stepping back
  into a result lands on its last page. The address (`?seat=&round=&step=`, `docs/architecture.md`, Replays) resolves
  through the same index, every bad part falling back as the contract says, and never names a page. A continuous
  move (autoplay, a held button or key, a turning wheel) pauses on every page of a result and at the last stop
  (`isPauseStop`), so a result is read before the next deal.
- A replay is whole only when its recording reaches the game's end (`complete`); one that stops short, or that its
  reader cut at a damaged line, keeps what it holds, and the display says so on every stop and where it ends at its
  last, and its unfinished round shows no result.
- The narration (`narrateStop`) tells a stop from its own entries and the tables after them, never from a sentence
  the table stored: the table keeps no description. A draw names its tile only where the perspective shows the
  drawer's hand.
