# Table entity

The game table model and board UI. `entities/client` steps it; views read the tables it produces.

- `applyEvent` is the table's only transition: readonly state in, a new table out. Nothing in this slice folds a
  sequence of events.
- The table holds what its source showed, never a second model per source: a live seat knows only its own tiles, so
  other hands are counts; a replay shows every hand. Another seat's draw moves the table when its notice arrives,
  never inferred from a later discard.
- A kan is the server's meld event, which comes before anyone may rob it (chankan); the client never builds a kan
  from a prompt or a result.
- **Out of order is a desync** (`PHASES_TAKING`). A handler that
  meets an impossible state throws `DesyncError`, never returns the state unchanged: the live client recovers from
  that error alone.
- **Scores come from the server.** A round end's wire `scores` are pre-payment and post-deposit; settle each player at
  that score plus `scoreChanges`, never from the prior state, so a deposit is never deducted twice. A collected
  stick's value (`riichiStickValue`) is a game setting the table keeps. A snapshot's scores
  already hold every deposit and a game end's standings the leftover sticks paid; take both as they are. The game's
  end takes the server's placement and uma/oka, never recomputed; leftover sticks are the server's `lr`, never the
  table's count. A table out of step (`inStep`) names no last round in how the game ended.
- **A result is the server's alone.** Its dealer, dora indicators and nagashi seats come from the round end, never
  the table, so a result shown out of step is still right. The one exception is a ron's robbed kan, read from the
  loser's melds: a table out of step that missed the kan's meld shows that ron as dealt in. The limit's name
  (`handLimitName`), a yaku's yakuman count, each winner's honba bonus and what a liable (pao) seat pays are the
  server's; the client words them and never works them back from points, han or yaku ids. A score map missing a seat
  is a desync.
- The live wall starts at the round-start or reconnect snapshot's authoritative count. Each genuine private draw or
  public draw notice subtracts one, including kan replacements and AI draws; a re-sent private tile already in the
  hand subtracts nothing.
- A riichi's deposit (the declarer's score and the table's sticks), the sticks a round end leaves, a round's number
  within its wind (`roundInWind`) and a chankan prompt's kan type are the server's, never counted or inferred. A pao
  assigned changes nothing the table shows; the result names the liable seat.
- The latest discard is the server's on reconnect (`ld`); the client never infers it. Any draw ends it.
- An AI stand-in for an absent human (`aiStandIn`) shows as the seat being away (its name red), never as an AI
  participant; a seated AI participant is unmarked on the board (the seating and game end mark it "AI").
- The board marks no tile playable and no offer source: that is the client mapper's.
- Board motion is presentation only; its look is `docs/game-client-look.md` (Tile motion), the player's Animations
  switch turning it off as the system's reduced motion does (`data-motion` on the board, the `reduced-motion` mixin),
  and it never delays the
  table, decisions or server input: a hold delays only the picture of a draw, the viewer's, an opponent's or the
  round's opening one. The mapper preserves physical tile ids across hands, rivers and both tiles of an
  added-kan stack; concealed hands keep anonymous slots, never invented ids, and an id reused in a new round never
  animates from its place in the previous round. `animateBoard` follows `sizeBoard` on GameBoard's root, so it
  measures destinations after the geometry is written. Native effects detach before lit changes the DOM and rebind
  by physical tile key with their timing preserved; a concealed hand's pending close ends at once when that seat's
  hand changes. A delayed slot motion is never a WAAPI `delay`: it waits paused at its start and a cancellable timer
  releases it, one timer per distinct delay of a played plan, so a hand's slots start together. The release sets its
  start time to the timeline's current time and never uses `play()`: WebKit keeps the creation start on `play()` while
  another animation runs, so the slide would finish at once. Its release timing runs on the `performance.now` timeline, never `browserClock`.
- The board's geometry is the slice's: `lib/board-geometry.ts`'s `boardGeometry`, a pure function from the board's
  box and the slots its page fills to a frozen result, its facts once in `lib/board-constants.ts` (the river's rows in
  the tile slice's `river-shape.ts`), and `ui/board-geometry-directive.ts`'s `sizeBoard` on GameBoard's root, the one
  place that measures the board and writes the result. What it lays out is the spec's (`docs/game-client-look.md`,
  Composition and Proportions). `lib/strip-layout.ts`'s `stripLayout` lays out a strip's melds from what it holds;
  `sizeBoard` takes it beside the slots and never hands it to `boardGeometry`, so contents never move a place.
  GameBoard never binds `style` on its root, which would clear what `sizeBoard` wrote.
- The board has no camera (`docs/game-client-look.md`, Principles). `lib/table-view.ts`'s `tableView` is that view of the geometry, and its seam
  (`boardViewValues`, `surfaceViewValues`: the pieces' `--geo-camera-*` transforms, the `--geo-shown-*` anchors of the
  calls and the felt's fields) is a deferred no-op kept for a later camera. Nameplates use the shell geometry directly
  so their anchors track the hand areas on resize and stay fixed throughout play.
- Replay records decode only through the lazy replay route (`model/replay-codec.ts`; the format is
  `docs/architecture.md`, Persistence). The numeric metadata registry mirrors the Go server's
  (`backend/game_v2/internal/wire`); the shared golden pins both registries.
- The table keeps the recorded aka-dora flag; all board and result tile mappers use it.
