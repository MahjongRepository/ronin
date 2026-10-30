# Table entity

The game table model and board UI. The client dispatcher (`entities/client`) owns stepping it; the
replay view, the live game and the storybook read the tables it produces.

- `TableState` / `PlayerState` (`model/types.ts`) are readonly, and `applyEvent` (`model/`) is the
  table transition: the next table after one `TableEvent` (a replay event, a seat control line, the
  reconnect snapshot, a seat's human leaving or returning), never changing the one it was given. It
  is the table's only transition; nothing in this slice folds a sequence of events itself.
- The table holds what its source showed, not a second model per source. A seat's closed hand is
  the tile ids it was shown plus a count of tiles held face down: a live seat knows only its own
  tiles (the deal's `myTiles`, the snapshot's), so every other hand is a count. Other seats' draws
  go only to the drawing seat, so they reach the table through the public event that follows them:
  a hidden hand of 3n+1 that discards or declares its own kan drew unseen first, and a round that
  ends on a seat's own draw (its tsumo, its kyuushu) settles that draw at the round end; a hand
  already holding it (a snapshot's 3n+2) is not counted twice. The wall shrinks then, and the turn
  moves to that seat. Between a hidden seat's draw and its first public event the wall reads one
  high and the hand shows 13: the protocol sends nothing to infer the draw from, and that lag is
  accepted. A replay shows every hand, so its counts stay 0. A draw of a tile the hand already
  holds is the one a reconnect re-sends: it marks the drawn tile and takes nothing from the wall. A
  round end writes the hands it reveals (its winners', a draw's tenpai hands) into the table as
  known tiles.
- A closed or added kan open to chankan shows as declared (`kan_declared`, a table event no message
  carries as such) before it resolves: its tiles leave the hand for the kan once, after the
  declarer's unseen draw joins its count, with no replacement draw or dora, since the server
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
  asks (the live game, until the player dismisses it).
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
- Seat marks: `aiStandIn` says an AI player holds the seat for its human, from a replay's seat
  control lines or the live `player_left` / `player_reconnected` (which name the player, not the
  seat, so the table finds the seat by name). The snapshot's AI flag cannot tell a bot from a
  stand-in, so it rebuilds no `aiStandIn`, only `isAiPlayer`; a `player_reconnected` clears both,
  since the named human controls the seat again whatever the snapshot said. The nameplate marks a
  stand-in the source named as one ("Away": left or absent) apart from an AI player ("AI"): after
  a reconnect a stand-in reads as an AI player, and a live seat never hears of a participant absent
  at the first deal (no `player_left` is sent for one that never joined) until a snapshot.
- `buildActionSteps` picks the replay's stop points from the timeline's step events, folding
  bookkeeping events (a new dora, game start, the first draw of a round) into the step before; an
  entry with no replay event (a seat control line, a line that did not parse) folds into the step
  after, so a seat's AI replacement shows from the move after its line. `buildNavigationIndex` maps
  steps to rounds and turns.
- `lib/board-mapper.ts` turns a table into the display state the `ui/` components render, from a
  perspective that is an input, not the dealer: which seat sits at the bottom, and whether every
  known hand shows face up (a replay) or only the bottom seat's. A known tile keeps its id;
  concealed tiles render as backs from the count; melds are laid out as faces; a riichi
  declaration's discard lies sideways, or when called, the declarer's next discard left in the
  river; the table's latest discard (`lastDiscardSeat`: set by a discard, cleared by any meld or kan
  declaration and a new deal; a reconnect's snapshot sets it when the seat in turn holds 3n+1 tiles and
  a river, since the server keeps the turn on a discarder while its discard is offered) is marked while
  it lies in its river. Each seat's nameplate (`BoardNameplate`) carries its name, seat wind, score, dealer,
  turn (only while a round plays), riichi and AI marks, and its signed difference from every other seat's
  score; the plate shows the name and marks, the centre each seat's wind, score and riichi stick on its
  side, and the board shows the differences from a hovered or pinned plate there by stylesheet alone.
  The pin is the view's state (`ScoreDiffPin`), never the table's. The centre also keeps the round and
  the wall; the dora panel the sticks. The board marks no tile playable: that is the client's
  mapper's, from a decision this slice does not know.
  `ui/board-overlay.ts` picks the panel a table shows over its board (the seating, a round's
  result, the standings) for every board that shows a table.
- `model/replay-file.ts` reads a replay file: it refuses one whose version line is not
  `REPLAY_VERSION` and hands back each event line as a JSON object for the dispatcher to parse
  (`parseReplayLine`), reporting a line that is not one without dropping the rest.
  `replayLineTableEvent` keeps the replay-only distinction: a replay event or seat control line
  moves the table; any other message (a prompt, an error, a furiten notice) never belongs in a
  replay and is reported.
