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
  ends on a seat's own draw (its tsumo, its kyuushu, its robbed kan) settles that draw at the round
  end; a hand already holding it (a snapshot's 3n+2) is not counted twice. The wall shrinks then,
  and the turn moves to that seat. Between a hidden seat's draw and its first public event the
  wall reads one high and the hand shows 13: the protocol sends nothing to infer the draw from, and
  that lag is accepted. A replay shows every hand, so its counts stay 0. A draw of a tile the hand
  already holds is the one a reconnect re-sends: it marks the drawn tile and takes nothing from the
  wall. A round end writes the hands it reveals (its winners', a draw's tenpai hands) into the
  table as known tiles.
- The draw, discard and meld handlers throw on an impossible state (a tile neither shown nor
  covered by the count, a missing player or caller); a new check throws the same way rather than
  returning the state unchanged. The other handlers tolerate a missing player or result.
- A round end's wire `scores` are taken after the riichi deposits and before the round's payments.
  `applyEvent` settles each player at that score plus its `scoreChanges` (the aggregated map, for a
  double ron too), never from the prior state, so a deposit is not deducted twice; the result keeps
  the pre-payment map for the overlay, which shows the score before payment and its delta.
- Seat marks: `aiStandIn` says an AI player holds the seat for its human, from a replay's seat
  control lines or the live `player_left` / `player_reconnected` (which name the player, not the
  seat). The snapshot's AI flag cannot tell a bot from a stand-in, so it rebuilds no mark.
- `buildActionSteps` picks the replay's stop points from the timeline's replay events, folding
  bookkeeping events (a new dora, game start, the first draw of a round) into the step before; an
  entry with no replay event (a seat control line, a line that did not parse) folds into the step
  after, so a seat's AI replacement shows from the move after its line. `buildNavigationIndex` maps
  steps to rounds and turns.
- `lib/board-mapper.ts` turns a table into the display state the `ui/` components render, from a
  perspective that is an input, not the dealer: which seat sits at the bottom, and whether every
  known hand shows face up (a replay) or only the bottom seat's. A known tile keeps its id;
  concealed tiles render as backs from the count; melds are laid out as faces; a seat an AI player
  holds for its human is marked (in its wind badge). The board marks no tile playable: that is the
  client's mapper's, from a decision this slice does not know. `ui/board-overlay.ts` picks the
  panel a table shows over its board (the seating, a round's result, the standings) for every
  board that shows a table.
- `model/replay-file.ts` reads a replay file: it refuses one whose version line is not
  `REPLAY_VERSION` and hands back each event line as a JSON object for the dispatcher to parse
  (`parseReplayLine`), reporting a line that is not one without dropping the rest.
  `replayLineTableEvent` keeps the replay-only distinction: a replay event or seat control line
  moves the table; any other message (a prompt, an error, a furiten notice) never belongs in a
  replay and is reported.
