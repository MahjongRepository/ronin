# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`, which wins where
they disagree.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- **Sizes come from `boardGeometry` (TS).** The sizes, the geometry family, the chrome tier and every reserved
  footprint come from it, through its directive on `.game-board`; the styles place from them. Its chrome lengths (text,
  badges, counters, switches, callout cap) reach CSS as px on every tier, bridged in `game-board/_grid.scss`; the only
  per-tier literals left are the phone's switch font, the small pill's inline padding, the debug log's corner, and the
  small-chrome desktop's decision text (16px) and decision gap in `_decision-controls.scss`.
  Family and chrome branches read the emitted `data-board-family` / `data-board-chrome`, never a CSS query
  of the board's box (nor
  `@container style()`, which Safari 16.4 lacks); container queries remain only for content-responsive rules. The
  family and chrome mixins are `game-board/_queries.scss`'s, which emits no CSS, so a lazy chunk's stylesheet (the
  replay's) can use them: a nested rule's selector takes the attribute inside `:where()` on its board compound, or
  behind a `:where(.game-board)` where it names none, keeping its specificity and place; a top-level block names the
  board itself.
- **The shell is a grid from the geometry's tracks; the pinwheel is local.** `boardGeometry` places GameBoard's slots
  (the corner, the switches at the band's start, the band end, the notices' field and its column beside a panel, the
  own row) as areas and emits the grid's templates (`--geo-shell-columns` / `--geo-shell-rows`, each area's edges a
  named line); `.board-layout` and `.board-table` lay them out and each slot takes its `grid-area`, aligned the way its
  contents stand in it. A slot's place is never a CSS formula: what its contents read (`--actions-*`,
  `--switches-*`, the field's height, which the notices' clamp reads as `max-height`) comes from the geometry too.
  The core's pinwheel (centre, rivers), the badges and the counters stand absolutely over the grid, and so do the
  replay's moves in the switches' place (from the band end, by the geometry's lengths) and its status over a
  smaller board's panel.
  Upright live boards keep their switches in a horizontal row with Pass and the timer to its right.
  Extra offers may wrap above into the wider space short of the right strip; the left strip ends above the switches.
  The own hand and core keep their sizes and places.
- **The panel's free box is the geometry's.** `boardGeometry` reserves it from the slots GameBoard fills (live play's or
  a replay's band) and the family's places; the overlay centres the panel on the board within its `--geo-overlay-*`
  insets, live and replay alike, over the cog where they reach it. The cog reserves no room in the strips: in landscape
  its corner slot ends inside the right strip's deepest reach with a gap, keeping its target clear of the melds.
  Where the top hand leaves too little room beside it, the corner starts below the top strip and badge.
  Upright it stays at the board's top right. The notices' field is reserved whether a
  notice shows or not, so no notice changes the panel's box or tiles. The panel's tile unit stays `--board-unit`, from
  that box's width and the board's height: one from `--rw` would draw a phone's result at 17px tiles where its box holds
  32px, an upright one's at 11px.
- **One source per fact.** The directive writes the sizes as `--geo-<name>` on `.game-board`; one rule (`_grid.scss`)
  maps those the styles read onto the lengths' own names on `.board-layout` and `.board-overlay`, inside `:where()` so
  it keeps (0,2,0); a name a family does not emit stays unset on its board, where nothing reads it. No CSS solve
  remains, so a board without `data-board-family` (not yet measured) hides its layers. A fact both sides need is TS's,
  emitted as a length (the chrome px, the river's footprint, the face floor, the latest discard's gaps); only what a
  container query needs stays Sass, beside a note naming its TS mirror (the decisions' gap and a win's rise), and the
  page's 10px gutter, which the page holds before the board is measured. A narrow desktop, best-effort in the spec's
  support tiers, reads the left strip's drawn depth for its notices (a margin on the field's slot): past the deepest
  strip its field falls under the 7.5em floor (6.2em at 780x580, none at 1080x880), a trade-off that tier accepts.
- **The replay fills live's slots.** GameBoard's band end (`.board-actions`, the decisions' place) holds live's
  decisions or a replay's group, its field (`.board-notices`) the notices and a replay's status; the band end's lengths
  (`--actions-*`, its room for a live row or a replay's group from the band the page fills) are the geometry's, so
  what stands beside it reads them.
  `_replay-state.scss` places no slot: it keeps the seating-on-the-centre-block rule, the controls' looks and their
  arrangement inside the band end (the moves before the options, upright the options over them, the moves in the
  switches' place where the band shares the core's corners) and the spec's panel-only exception. Upright, the band
  end's row and the own badge's lane are the geometry's (`--geo-actions-bottom`, `--own-lane`).
- **A phone's composition is its own.** `boardGeometry` solves its river tile as the largest that fits and its own
  tile on its own scale from the box: at least 4/3 of the river tile, at most a full hand clear of both side strips'
  stacked depth, never under 36px; within that, the largest whose decisions' place under the right badge holds a
  win's stack, else the least at that river tile, so that bound never lowers the river tile. Its band's controls float
  in the gap above the hand, its chrome follows the river tile with the control floor, and its right hand's place
  (the band row stepping in) is computed there too, never with a length switch.
- The centre is square: `--w` and `--c` are its side, `--hx` and `--h` its half-side. Its text follows `--c`.
  Every family's centre is at least six river tiles tall; the geometry fits that centre and the rivers together.
  Desktops tighten the top separation before reducing tiles. Phones and upright boards also keep their text floors.
- Lengths CSS computes are registered with `@property` (`<length>`), so each computes once to pixels; an
  unregistered chain grows with every reference until a browser drops the declaration. A bridged length is px already.
- **Layout measurements**: the board's geometry directive and the notices' clamp. Motion snapshots only measure
  existing tile positions for temporary copies; they never feed the layout solve. A choice between placements is
  made in TS, never with a length switch (`clamp(0px, x * 1000, 1px)` as a 0/1 boolean) or a `9999px` sentinel;
  content reaches the strips through `stripLayout`, never fed into the box's sizing.
- **One strip primitive, four seats.** GameBoard's `Strip` draws every seat's hand and melds; an opponent's is a grid
  area the geometry sizes to its turned footprint (a side lane's reserve along its hand's room, the top one's
  stacked depth along its line), its frame turned to the seat inside (a rotation, never `writing-mode`, which leaves
  each tile's SVG unturned) from the area's corner where its hand starts. Every seat keeps its melds in one line to its owner's right,
  oldest at the far end; side melds never wrap into parallel columns. `stripLayout` scales all melds
  together to fit, using their actual footprints to clear the geometry's reserved badge, switches
  and own row. `stripLayout` (`entities/table/lib`) stays separate from
  `boardGeometry`; the directive writes its placements as `--<seat>-meld-<n>-*` lengths and each
  side strip's drawn depth as `--left-depth` / `--right-depth`. Contents never enter the viewport's solve. The own row's melds take `--own-meld-w` and the upright hand's lead steps back by `--own-shift`, both from `ownMeldLayout` over the melds' structure, never from the hand's current width. No tile size, hand start or laid meld's place may follow transient content (a draw, a discard, an offer): a stylesheet never fits tiles to the room content leaves.
- **One river primitive, four seats.** GameBoard's `River` draws every seat's river on the tile slice's shape
  (`river-shape.ts`), its overflow an explicit per-seat policy (`RIVER_OVERFLOW`: a side river wraps a fourth row, a
  top or bottom one runs its third row on); it stays in the core's pinwheel, absolutely placed, its area a normal
  river's turned footprint with its frame turned to the seat inside (a rotation, never `writing-mode`) from the area's
  corner where the first row starts. The geometry reserves nineteen discards for top and bottom rivers when placing
  slots and badges; a rarer longer third row may overflow that reserve. The styles read only the bottom river's
  reserved run-on reach (`--reach-bottom-right`).
- **Places are fixed per viewport.** Badges, an opponent's full hand reach, the decisions' place, the notices' place
  and the replay's controls never move with tile counts or what a stop shows; nothing else enters a full hand's reach.
  A place beside a side strip keeps clear of the strip's deepest reach, never its depth as drawn.
- The notices never cover a tile within its reserved reach, a plate, the centre, a decision control or a panel.
  Rarer top and bottom third rows past nineteen discards may extend under them. A panel never covers the
  page's corner or the replay's controls.
- The own hand's tiles are the board's largest: a phone's for touch; off a phone 1.6 of the river tile within its
  family's caps, never under 4/3 of it, every other hand and river at the river tile. No meld face
  goes under 13px wide; scaled text keeps a 10px
  floor (a safety limit, not a design size).
- A round result fits its panel whole at every supported size; only on a board too small for it does it scroll its
  yaku, value, indicators and score rows in place, keeping its head and the viewer's controls whole, every other part
  that shares a row with a scroller scrolling too.
- A panel sized by its content reserves its scrollbar's gutter (`scrollbar-gutter: stable`): the overlay's auto
  track takes the panel's height before a classic scrollbar narrows it, so without the gutter the scrollbar wraps a row
  (the game end's actions) the track never grew for. The round result, its width set, keeps no gutter.
- Pages never clip the board: `.board-page` gives it the safe area, and a 10px gutter on every board but a phone's.
  The own row stands at least its edge's depth off the bottom. Top and bottom rivers reserve nineteen discards;
  longer third rows still render but may clip at the board edge or extend under peripheral elements.
- **The gutter follows the family, decided once.** The board's box without the gutter, less on each edge what a
  10px gutter adds beyond the safe inset, is classified once: a phone takes no gutter and the unguttered box, any
  other family the 10px gutter on that box. Classifying the guttered board instead would flip the family at the
  threshold (desktop gutter, phone box, no gutter, desktop box). `.board-page` holds the gutter (10px, 0 around a
  phone's board) and the safe insets as registered lengths, which the directive reads in px; a gutter change it finds
  while the observer delivers (into or out of a phone) waits a frame, since it resizes the observed board.
- Every tile's box and material is `_tile.scss`'s; each region sets `--board-tile-w`. A sideways tile (a called meld
  tile, a riichi discard) is an unturned box as long as a tile is tall with only its face turned: a turned box of a
  fractional size paints off its layout box, below its row's baseline. Flying tiles use that same
  material with animated dimensions and orientation; their grouped depth stays on an unturned wrapper, so the
  light does not rotate with the face. Native reflow stays inside its original group. Side hands isolate separate
  tile-depth and seam-mask layers below their faces: masks must never enter a shadow filter, or a separated tile
  casts a detached rectangular edge. A seam's mask stands on the tile whose edge does not fall into that seam (the
  later tile on the left, the earlier on the right), so a tile a reflow carries off keeps its whole edge attached
  instead of a mask riding with it cutting a detached sliver. Other groups keep their shared shadow. Hands and
  rivers use positional offsets: a transform creates per-tile stacking contexts that lift the side strips' seam
  masks over neighbouring faces and depth. Laid melds have no seam masks and transform their tile wrappers to
  interpolate position and size. Reveal backs stay inside the native hand slots, absolutely placed over the hidden
  faces so they retain the hand's depth and gap masks without changing its layout.
- The rivers' shared edge and shadow come from `.board-rivers` (`_tile.scss`), the unturned layer holding all four,
  never from a turned river frame's own filter: Firefox on macOS draws a turned element's filter unturned and clipped
  to its box.
- **Layers come from one scale.** Every `z-index` is a `$layers` name (`game-board/_queries.scss`), never a literal.
  `.game-board` isolates its layers from the page's. `.board-layout` and `.board-table` form no stacking context, so
  the notices and a replay's band end stand over the overlay's dim by their layers in the board's own context; an
  `isolation`, `transform`, `filter`, `opacity` or `z-index` on either would drop them under it.
- Held-back tiles are greyed out at their normal size and position, with their edge and shadow kept;
  switch states differ by more than colour.
- The live game's rotate panel depends on viewport dimensions alone, never the input device.
  Narrow portrait desktop windows get the same panel as phones; replay and storybook boards remain readable upright.
