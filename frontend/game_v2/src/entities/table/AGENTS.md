# Table entity

The game table model and board UI. `entities/client` steps it; views read the tables it produces.

- `applyEvent` is the table's only transition: readonly state in, a new table out. Nothing in this slice folds a
  sequence of events.
- The table holds what its source showed, never a second model per source: a live seat knows only its own tiles, so
  other hands are counts; a replay shows every hand. Another seat's draw moves the table when its notice arrives,
  never inferred from a later discard. A draw of a tile the hand already holds is a reconnect's re-send: it takes
  nothing from the wall.
- A kan open to chankan shows as declared (`kan_declared`) before it resolves, with no replacement draw or dora; the
  meld that completes it takes nothing more from the hand.
- **Out of order is a desync.** `PHASES_TAKING` checks every event's phase before any handler runs. A handler that
  meets an impossible state throws `DesyncError`, never returns the state unchanged: the live client recovers from
  that error alone.
- **Scores come from the server.** A round end's wire `scores` are pre-payment and post-deposit; settle each player at
  that score plus `scoreChanges`, never from the prior state, so a deposit is never deducted twice. A collected
  stick's value (`riichiStickValue`) is a game setting the table keeps. A snapshot's scores
  already hold every deposit and a game end's standings the leftover sticks paid; take both as they are. The game's
  end takes the server's placement and uma/oka, never recomputed; leftover sticks are the server's `lr`, never the
  table's count. A table out of step (`inStep`) names no last round in how the game ended.
- **A result is the server's alone.** Its dealer, dora indicators and nagashi rivers come from the round end, never
  the table, so a result shown out of step is still right. The limit's name (`handLimitName`), a yaku's yakuman
  count, each winner's honba bonus and what a liable (pao) seat pays are the server's; the client words them and
  never works them back from points, han or yaku ids. A score map missing a seat is a desync.
- The live wall starts at the round-start or reconnect snapshot's authoritative count. Each genuine private draw or
  public draw notice subtracts one, including kan replacements and AI draws; a re-sent private tile already in the
  hand subtracts nothing. An empty wall on a new draw is a desync. Replays retain each draw's recorded count.
- A riichi's deposit (the declarer's score and the table's sticks), the sticks a round end leaves, a round's number
  within its wind (`roundInWind`) and a chankan prompt's kan type are the server's, never counted or inferred.
- The latest discard is the server's on reconnect (`ld`); the client never infers it. Any draw ends it.
- An AI stand-in for an absent human (`aiStandIn`, "Away") is never shown as an AI participant ("AI").
- The board marks no tile playable and no offer source: that is the client mapper's.
- Board motion is presentation only; its look is `docs/game-client-look.md` (Tile motion), the player's Animations
  switch turning it off as the system's reduced motion does (`data-motion` on the board, the `reduced-motion` mixin),
  and it never delays the
  table, decisions or server input. The mapper preserves physical tile ids across hands, rivers and both tiles of an
  added-kan stack; concealed hands keep anonymous slots, never invented ids, and an id reused in a new round never
  animates from its place in the previous round. `animateBoard` follows `sizeBoard` on GameBoard's root, so it
  measures destinations after the geometry is written. Native effects detach before lit changes the DOM and rebind
  by physical tile key with their timing preserved.
- The seating panel is the game's start and its end: the seats in wind order with the round on the table (live, the
  client's opening screen over the dealt table, `tableSeatingPanel`; a replay's start), then in placement order with
  their scores and uma/oka results once the game ends. `tablePanel` itself shows nothing before the first deal.
- The board's geometry is the slice's: `lib/board-geometry.ts`'s `boardGeometry`, a pure function from the board's
  box and the slots its page fills to a frozen result, its facts
  once in `lib/board-constants.ts` (the river's rows in the tile slice's `river-shape.ts`), and
  `ui/board-geometry-directive.ts`'s `sizeBoard` on GameBoard's root, the one place that measures the board and writes
  the result. `lib/strip-layout.ts`'s `stripLayout` lays out a strip's melds in those rooms from what it holds, which
  `sizeBoard` takes beside the slots and never hands `boardGeometry`. Every seat's melds stay in one line toward their owner's
  right, oldest at the far end. The geometry reserves enough length for four kans (a phone's as much of that line as its box
  holds; `stripLayout` lays a denser seat's melds on past the line at the face floor) and supplies reserved footprints;
  the content layout scales ordered melds together without moving the hand or controls. GameBoard never binds `style` on its root, which
  would clear what `sizeBoard` wrote.
- `model/replay-file.ts` refuses a file whose version is not `REPLAY_VERSION` and reports a bad or live-only line,
  never skipping it into a recording that looks whole.
- Replay storage is concatenated MessagePack records, decoded only through the lazy replay route. The numeric metadata registry mirrors Python; the shared golden pins both registries.  A damaged record stops playback at its preceding readable prefix and names its record position.
- The table keeps the recorded aka-dora flag; all board and result tile mappers use it. A live game always shows red fives (its game start sets `hasAkadora`).
