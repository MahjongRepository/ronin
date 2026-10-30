# Table entity

The game table model and board UI. The client dispatcher (`entities/client`) owns stepping it; the
replay view, the live game and the storybook read the tables it produces.

- `TableState` / `PlayerState` (`model/types.ts`) are readonly, and `applyEvent` (`model/`) is the
  table transition: the next table after one `TableEvent` (a replay event, a seat control line, the
  reconnect snapshot, a seat's human leaving or returning, another seat's draw notice), never
  changing the one it was given. It
  is the table's only transition; nothing in this slice folds a sequence of events itself.
- The table holds what its source showed, not a second model per source. A seat's closed hand is
  the tile ids it was shown plus a count of tiles held face down: a live seat knows only its own
  tiles (the deal's `myTiles`, the snapshot's), so every other hand is a count. Another seat's draw
  reaches a live seat as its notice (`draw_notice`, a table event of its own that never opens a
  decision): the drawer's count gains a tile, the wall loses one and the turn moves to it, when the
  draw happens, never inferred from a later discard (a call window may still be open). A replay
  shows every hand, so its counts stay 0. A draw of a tile the hand already
  holds is the one a reconnect re-sends: it marks the drawn tile and takes nothing from the wall. A
  round end writes the hands it reveals (its winners', a draw's tenpai hands) into the table as
  known tiles and names their seats (`revealedSeats`), which every perspective shows face up until the
  next deal; a reconnect's snapshot of a round advance reveals them the same way.
- A closed or added kan open to chankan shows as declared (`kan_declared`, a table event no message
  carries as such) before it resolves: its tiles leave the hand for the kan once, with no
  replacement draw or dora, since the server
  completes the kan only once nobody robs it. A live seat sees it from its chankan prompt (the kan
  type then follows the declarer's pon or the added kan already shown, as the server decides), and
  a round end or reconnect snapshot whose win robbed a kan shows it from `robbedKan` unless it is
  shown already; the snapshot still holds the robbed tiles in the hand, since the server never
  completes the kan. A meld that completes a shown kan replaces it and takes nothing more from the
  hand. A replay records no line for the declaration, so the dispatcher takes a replay's round end
  that robbed a kan in two steps, the kan declared and then the result, and the replay stops on
  the kan. A seat control line between the declarer's draw and that round end therefore shows from
  the kan's stop: the replay cannot tell whether the seat changed before the declaration or after.
- The draw, discard, meld, kan declaration and riichi handlers throw on an impossible state (a tile
  neither shown nor covered by the count, a missing player or caller); a new check throws the same
  way rather than returning the state unchanged. The other handlers tolerate a missing player or
  result.
- Riichi deposits on `riichi_declared`, which the server sends only once the declaration's discard
  passes without a ron (a ronned declaration discard deposits nothing): one stick onto the table,
  1000 (the server's `riichi_cost` default, which no live message carries) off the declarer. The
  reconnect snapshot's scores and sticks already hold every deposit and are taken as they are.
- A round end's wire `scores` are taken after the riichi deposits and before the round's payments.
  `applyEvent` settles each player at that score plus its `scoreChanges` (the aggregated map, for a
  double ron too), never from the prior state, so a deposit is not deducted twice; the winners'
  collected sticks leave the table, a draw's stay. The result keeps the pre-payment map, from which
  the result panel shows a page's deltas and the scores after every payment through that page: a
  double ron's first page ends at the scores after its first winner alone, its last at the scores
  the table settled. A game end's standings already hold
  the leftover sticks paid to the winner (`lb`); the table takes them and empties the sticks, and
  keeps the last round's result, which `boardOverlay` shows over the standings only when the view
  asks (the live game, until the player dismisses it, and again when the player reopens it).
- The table keeps every finished round as a `RoundRecord` (`roundHistory`) for the final standings'
  ledger, built from its own round end or taken whole from a reconnect's snapshot history, which
  names the same fields (the result type and an abortive draw's reason included), so a reconnect
  rebuilds the ledger the seat built. A record's payments exclude riichi deposits; the ledger nets
  each standing riichi's deposit out of its round, so the rounds and the leftover sticks add up to
  each final score. `lib/standings-display.ts` maps an ended table to the standings (seats in the
  server's placement order with its uma/oka results, never recomputed; a ledger row per record;
  the leftover sticks), which `ui/standings-panel.ts` renders. A ledger cell's text is its change, net of
  a riichi deposit; a round with no payments names each seat's tenpai on a draw that judges it, so a
  deposit never hides another seat's tenpai. The mapper, the panel and their stylesheet are one lazy
  chunk (`ui/standings.ts`, started by `startStandingsLoad`), so `boardOverlay` draws the standings only
  through the renderer the view hands it. Rounds hidden under the sticky totals show a shadow over the
  totals by CSS alone: the sheet paints it at the totals' height, which their fixed row height gives,
  under the transparent rows, and the last row, opaque, covers it once nothing more is hidden.
- A player's name in a panel (the result's scores, the standings' columns, the seating) is
  `PlayerName`: a narrow column shortens it in the middle, keeping its end (`nameParts`), as the
  nameplate does, so AI players stay told apart.
- A round end's result (`RoundEndResult`) keeps what the panel shows: per winner its hand, value
  (`handResult.points`, the hand alone), dora kinds, ura indicators, its own payments, honba bonus
  (its gain beyond hand value and sticks), sticks and pao seat; for a draw its kind and the seats it
  names (tenpai/noten with hands, nagashi, kyuushu declarer, triple-ron callers). Per-winner payments
  only describe: the table settles from the aggregate, once. `roundEndPages` gives a page per
  winner (a double ron's two) or the draw's one; the view picks the page, and `roundEndPageAt` is
  the one place that clamps it to the pages and counts them. `lib/round-end-display.ts` maps a
  result at a page to the panel's display state (faces, names, limit, notes, score rows, the
  clamped page and the count), which `ui/round-end-display.ts` only renders. A limit's name
  (`handLimitName`) comes from the points the server paid, 4x (6x for the dealer) the limit's basic
  points, never from han, so it follows whatever kiriage, kazoe and yakuman rules the game used.
- The wire's round number counts every deal of the game; a round's name ("East 1", "South 3") is
  its number within its wind, the dealer's distance from the first dealer (`roundInWind`), which
  the table keeps from the game start or, on a reconnect, the snapshot's first listed round.
- Seat marks: `aiStandIn` says an AI player holds the seat for its human, and why: from a replay's
  seat control lines and the live `seat_control` messages, which parse into the same lines, and from
  the reconnect snapshot, which names such a seat (`sr`) apart from an AI player (`ai`). The
  nameplate marks a stand-in ("Away": left or absent) apart from an AI player ("AI"). A participant
  without a connection at the first deal (never joined, or gone during the game start pause) is told
  then, ahead of the deal.
- A replay's cursor contract is pure functions over one navigation index (`buildNavigationIndex`),
  which the controls, the round list, the address, the ledger and autoplay all move through. A stop is a move: a deal (with its first draw), a draw, a discard (with the riichi its
  passing deposits, so the stick shows on the declaring discard), a call, a kan declared open to
  chankan, a round's result, the game's end. Bookkeeping (a deal's first draw, a new dora, an
  accepted riichi) belongs to the move before it; annotations (the game start, a seat control line)
  are never a stop. One rule places both (`buildActionSteps`): a move's stop runs through its last
  bookkeeping entry, past any annotation between, and an annotation after it shows from the next
  stop. So a seat that changes hands in a riichi's call window (the server records the line before
  the acceptance its AI player's pass brings) is told on the declaring discard, which shows the
  deposit, and otherwise a seat's change of hands is told and marked from the move after its line.
  Every stop is a timeline state; none is a table patched outside the dispatcher. The
  replay opens on the first deal: nothing before it is a stop. Stops are numbered within their
  round from 0 at its deal, the game's end the last round's last stop, and a round's result
  (`roundResultCursor`, where the standings' rows go) the stop whose table shows it ended. A result stop has a page
  per winner; stepping pages through them, and stepping back into a result lands on its last page.
  The address (`?seat=&round=&step=`, `docs/architecture.md`, Replays) resolves through the same
  index, every bad part falling back as the contract says, and never names a page.
  A continuous move (autoplay, a held button or key, a turning wheel) pauses on every page of a
  result and at the last stop (`isPauseStop`), so a result is read before the next deal.
- A replay is whole only when its recording reaches the game's end (`complete`); one that stops
  short, or that its reader cut at a damaged line, keeps what it holds, and the display says so on
  every stop and where it ends at its last, and its unfinished round shows no result.
- The narration (`narrateStop`) tells a stop from its own entries and the tables after them, never
  from a sentence the table stored: the table keeps no description. A draw names its tile only
  where the perspective shows the drawer's hand.
- `lib/board-mapper.ts` turns a table into the display state the `ui/` components render, from a
  perspective that is an input, not the dealer: which seat sits at the bottom, and whether every
  known hand shows face up (a replay) or only the bottom seat's and the seats a result revealed. A known tile keeps its id;
  concealed tiles render as backs from the count; melds are laid out as faces; a tile another seat
  claimed has left the river for the meld that took it; a riichi declaration's discard lies sideways, or
  when called, the declarer's next discard left in the river; the table's latest discard
  (`lastDiscardSeat`: set by a discard, cleared by a call that claims it (chi, pon, open kan) and a new
  deal, kept through a draw and a kan from the hand, which claims none) is marked. A reconnect takes it
  from the snapshot (`ld`), which the server derives from the round's own discard history and leaves out
  when there is none or a call claimed it; the client never infers it. Each seat's nameplate (`BoardNameplate`) carries its name, seat wind, score, dealer,
  turn (only while a round plays), riichi and AI marks, and its signed difference from every other seat's
  score; the plate shows the name and marks, the centre each seat's wind, score and riichi stick on its
  side, and the board shows the differences from a hovered or pinned plate there by stylesheet alone.
  The pin is the view's state (`ScoreDiffPin`), never the table's. The centre also keeps the round and
  the wall; the dora panel the sticks. The board marks no tile playable and no meld as an offer's
  source (`sourceMeld`, a chankan offer's kan): both are the client's mapper's, from a decision this slice does
  not know.
  `ui/board-overlay.ts` picks the panel a table shows over its board (the seating, a round's
  result, the standings) for every board that shows a table.
- `lib/callouts.ts` says which calls a table event makes aloud (`eventCalls`, read with the tables it
  found and left, so a round end's winners come from its result and a kan the table already showed is
  not called again) and null for an event that is no move of its own, which leaves the calls shown; a
  kan's call names its tile type, so a live call can be told from another kan of the same seat. It
  holds `CALLOUT_MS`, the one length of a live call, which the board hands its stylesheet. The client's
  dispatcher keeps the calls, and a replay's display takes each stop's from its state
  (`ReplaySource.calls`), keyed by the stop.
- `model/replay-file.ts` reads a replay file: it refuses one whose version line is not
  `REPLAY_VERSION` and hands back each event line as a JSON object for the dispatcher to parse
  (`parseReplayLine`), reporting a line that is not one without dropping the rest.
  `replayLineTableEvent` keeps the replay-only distinction: a replay event or seat control line
  moves the table; any other message (a prompt, an error, a furiten or draw notice) never belongs
  in a replay and is reported.
