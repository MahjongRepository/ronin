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
  stick's value (`riichiStickValue`) is the one game setting the table keeps. A snapshot's scores
  already hold every deposit and a game end's standings the leftover sticks paid; take both as they are. The game's
  end takes the server's placement and uma/oka, never recomputed; leftover sticks are the server's `lr`, never the
  table's count. A table out of step (`inStep`) names no last round in how the game ended.
- **A result is the server's alone.** Its dealer, dora indicators and nagashi rivers come from the round end, never
  the table, so a result shown out of step is still right. The limit's name (`handLimitName`), a yaku's yakuman
  count, each winner's honba bonus and what a liable (pao) seat pays are the server's; the client words them and
  never works them back from points, han or yaku ids. A score map missing a seat is a desync.
- The live wall's count, a riichi's deposit (the declarer's score and the table's sticks), the sticks a round end
  leaves, a round's number within its wind (`roundInWind`) and a chankan prompt's kan type are the server's, never
  counted or inferred by the client.
- The latest discard is the server's on reconnect (`ld`); the client never infers it. Any draw ends it.
- An AI stand-in for an absent human (`aiStandIn`, "Away") is never shown as an AI participant ("AI").
- The board marks no tile playable and no offer source: that is the client mapper's.
- Board motion is presentation only. The mapper preserves physical tile ids across hands, rivers and both tiles
  of an added-kan stack; concealed hands keep anonymous slots, never invented ids. The board's motion directive
  captures positions before a render and measures destinations after its geometry directive. Its player owns
  temporary copies for cross-region travel and native wrapper animations for hand reflow. Native effects detach
  before lit changes the DOM, so geometry measures final positions, then rebind by physical tile key with their
  timing preserved. Flight copies keep complete material and interpolate size and orientation. A flying local
  tile forwards taps to its current native button, with its stationary hitbox disabled until arrival. Copies
  refresh disabled and selected feedback on input-only redraws without restarting travel. Motion never delays
  the table, decisions or server input. Sequential moves
  preserve unaffected flights in live play. Replay steps settle all prior tile movements before measuring the next
  move and omit the live discard pause; updates within one render task animate only the newest replay step.
  Reconnects, replay jumps,
  viewpoint changes, resizing, reduced motion and disposal clear copies and restore destinations. Initial mounts
  show their checkpoint immediately. Starting hands and indicators appear immediately at every deal; tile ids
  reused in a new round never animate from their positions in the previous round.
- The seating panel is the game's start and its end: the seats in wind order before the first deal, then in
  placement order with their scores and uma/oka results once the game ends.
- The board's geometry is the slice's: `lib/board-geometry.ts`'s `boardGeometry`, a pure function from the board's
  box and the slots its page fills to a frozen result (family, chrome, centre, sizes, the panel's free box in px, the
  board shell's grid tracks and the opponents' strips' rooms), its facts
  once in `lib/board-constants.ts` (the river's rows in the tile slice's `river-shape.ts`), and
  `ui/board-geometry-directive.ts`'s `sizeBoard` on GameBoard's root, the one place that measures the board and writes
  the result. `lib/strip-layout.ts`'s `stripLayout` lays out a strip's melds in those rooms from what it holds, which
  `sizeBoard` takes beside the slots and never hands `boardGeometry`. Every seat's melds stay in one line toward their owner's
  right, oldest at the far end. The geometry reserves enough length for four kans and supplies reserved footprints;
  the content layout scales ordered melds together without moving the hand or controls. GameBoard never binds `style` on its root, which
  would clear what `sizeBoard` wrote.
- `model/replay-file.ts` refuses a file whose version is not `REPLAY_VERSION` and reports a bad or live-only line,
  never skipping it into a recording that looks whole.
