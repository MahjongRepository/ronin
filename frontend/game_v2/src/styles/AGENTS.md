# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- **Sizes come from `boardGeometry` (TS).** The sizes, the geometry family, the chrome tier and every reserved
  footprint come from it, through its directive on `.game-board`; the styles place from them. Its chrome lengths (text,
  badges, counters, switches, callout cap) reach CSS as px on every tier, bridged in `game-board/_grid.scss`; a new chrome length comes from it, never a per-tier literal.
  Family, chrome and switch-form branches read the emitted `data-board-family` / `data-board-chrome` /
  `data-board-switches`, never a CSS query
  of the board's box (nor
  `@container style()`, which Safari 16.4 lacks); container queries serve only content-responsive rules. The
  family and chrome mixins are `game-board/_queries.scss`'s, which emits no CSS, so a lazy chunk's stylesheet (the
  replay's) can use them: a nested rule's selector takes the attribute inside `:where()` on its board compound, or
  behind a `:where(.game-board)` where it names none, keeping its specificity and place; a top-level block names the
  board itself.
- **The shell is a grid from the geometry's tracks; the pinwheel is local.** The table is centred, off a phone as
  wide as the own row and the two side lanes it stands between (a phone's a column of at least 25 river tiles),
  its side bars the rest of the width; `boardGeometry` places GameBoard's
  slots (the cog, the left bar's notices' field, furiten and switches' column, the right bar's replay column, the
  decisions' cluster, a desktop's toasts, the own row) as areas and emits the grid's templates (`--geo-shell-columns` / `--geo-shell-rows`, each area's edges a
  named line); `.board-layout` and `.board-table` lay them out and each slot takes its `grid-area`, aligned the way its
  contents stand in it. A slot's place is never a CSS formula: what its contents read (`--actions-*`,
  `--switch-*`, the field's height and a desktop's toasts', which the notices' clamp reads as `max-height`) comes from the geometry too.
  The core's pinwheel (centre, rivers), the plates (one rectangle in the core's corners on every board, its two
  columns and two rows the geometry's) and the
  counters stand absolutely
  over the grid, by the geometry's lengths, and so does a replay's status over a smaller board's panel.
- **A width-bound desktop's table is a frame of its own.** Where the board is taller than its table needs, the
  geometry emits `--geo-table-top` and `--geo-table-h`, and `.board-layout` stands there, that tall: every length,
  track and slot is in the table's frame, the zones' seams and fields reach its corners (their layer still covering
  the whole board), and the overlay, which spans the whole board for its dim, reads `--cy` shifted by the table's top.
  A height-bound board emits neither, its fallbacks the whole board.
- **The panel's free box is the geometry's.** Off a phone it is the table column, so the bars' notices and replay
  controls stay usable beside a panel; the overlay centres the panel within its `--geo-overlay-*` insets, live and
  replay alike, over the cog where they reach it. The cog stands at the right bar's top, in the board's top-right
  corner where the bar is narrower than its target and a gap. Off a phone the notices' field is reserved whether a
  notice shows or not, so no notice changes the panel's box or tiles. A phone's panel takes equal side gaps and stands
  centred (a replay's clear of the right bar, which holds its moves); only while a notice shows does it narrow, by
  `--geo-overlay-right-beside-notices`, to clear the notices, which over a panel stand in the right bar
  (`field-beside`). The panel's tile unit stays `--board-unit`, from
  that box's width and the board's height: one from `--rw` would draw a phone's result at 17px tiles where its box holds
  32px.
- **One source per fact.** The directive writes the sizes as `--geo-<name>` on `.game-board`; one rule (`_grid.scss`)
  maps those the styles read onto the lengths' own names on `.board-layout` and `.board-overlay`, inside `:where()` so
  it keeps (0,2,0); a name a family does not emit stays unset on its board, where nothing reads it. There is no CSS solve,
  so a board without `data-board-family` (not yet measured) hides its layers. A fact both sides need is TS's,
  emitted as a length (the chrome px, the river's footprint, the latest discard's gaps); only what a
  container query needs stays Sass, its TS mirror naming it (a phone's decision row and gap), and the
  page's 10px gutter, which the page holds before the board is measured. The notices' text is the geometry's
  (`--notice-text`): a phone's smaller where the left bar is narrower than 7.5 of its ems, down to 11px at the bar's
  floor; a desktop's toasts' the board's share, never under 14px; a desktop's notices over a panel, in the left bar's
  field, fitted to 7.5 of their ems the same way (`--field-notice-text`); a desktop replay's status in its own area
  (`info`, under the counters) fitted to 9 of its ems (`--status-text`), never under 13px.
- **Live decisions stand in one cluster; the bars hold the rest.** Off a phone live's decisions (`.board-actions`)
  stand in the core's bottom-right corner: past the bottom river's nineteen discards' reserve to short of the right
  strip's lane, under the right river's first tile and over the own row's melds' rise, in as many rows of
  `--decision-h` controls as its width needs. A longer river's tiles and, on a short window, the right river's first
  tiles may lie under it: the cluster stands over them (its layer, solid controls with `--action-lift`, the timer on a
  badge), and no table width or stack row is reserved for it. Its controls, the offers'
  (`.decision-controls__upper`, a box of none of its own there) and the band's (the pass, then the timer
  `--actions-band-w` wide, as one piece), wrap up from its bottom right, every label at the geometry's
  `--action-text`; the geometry holds the band in the corner from the same ems the stylesheet draws it with, so the
  two change together. A desktop's notices stand apart from the field as toasts of up to two lines in the core's
  bottom-left corner, under the left river's longest reach and over the own row (`toasts`), stacked down from its
  top, cut short with an ellipsis past their second line (the whole in the notice's title, the cut one opening the
  sheet), the last ones left out where the felt is short (the last shown its "+N"), under no panel only
  (`toast-board`), where a replay's status stands in `info`: over a panel they stand in the field, wrapping as a
  phone's do, the status with them. A replay's moves and options take
  the right bar's foot. Nothing stands between the bottom river and the own row. On a phone the right bar holds live's decisions
  whole, wrapping up from the timer at its foot, and a replay's column at its foot; the left bar the counters, the
  notices and the switches as a two-by-two block. `_replay-state.scss` places no slot.
- **One composition, two profiles.** Off a phone there is one desktop family: the river tile from
  the vertical stack, the own tile from the width a full hand between the side lanes keeps, 1.2 to 1.45 river
  tiles; no side strip's tile stands over the own row's span. A phone keeps the composition with its own profile: `boardGeometry`
  solves its river and own tiles together from the box (the spec's sizing rule), its own row spans the board under
  both lanes (in the shortest browser boxes, where above it the lanes cannot hold three kans or the right bar the
  offers, between them, the lanes and bars running down beside it), and its decisions stand in the right bar; a family difference is the geometry's, never a length switch.
- The centre is a rectangle in every family, `--c`/`--h` its height and `--w`/`--hx` its width: off a phone six river
  tiles wide by 4.5 tall, on a phone the height left over the own row. Its score rows and their inset follow the
  shorter of the two; the round and counts follow `--c` within the room `--w` leaves. The geometry fits the centre and the rivers together, at the spec's minimums (Proportions).
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
  together to fit, using their actual footprints to clear the own row. `stripLayout` (`entities/table/lib`) stays separate from
  `boardGeometry`. Contents never enter the viewport's solve. The own row's melds take `--own-meld-w` from `ownMeldTile` over the melds' structure, never from the hand's current width. No tile size, hand start or laid meld's place may follow transient content (a draw, a discard, an offer): a stylesheet never fits tiles to the room content leaves.
- **One river primitive, four seats.** GameBoard's `River` draws every seat's river on the tile slice's shape
  (`river-shape.ts`), its overflow an explicit per-seat policy (`RIVER_OVERFLOW`: a side river wraps a fourth row, a
  top or bottom one runs its third row on); it stays in the core's pinwheel, absolutely placed, its area a normal
  river's turned footprint with its frame turned to the seat inside (a rotation, never `writing-mode`) from the area's
  corner where the first row starts. The geometry reserves nineteen discards for top and bottom rivers when placing
  slots and badges; a rarer longer third row may overflow that reserve.
- **Places are fixed per viewport.** Badges, an opponent's full hand reach, the decisions' place, the notices' place
  and the replay's controls never move with tile counts or what a stop shows; nothing else enters a full hand's reach.
  A place beside a side strip keeps clear of the strip's deepest reach, never its depth as drawn.
- A round result fits its panel whole at every supported size; only on a board too small for it does it scroll its
  yaku, value, indicators and score rows in place, keeping its head and the viewer's controls whole, every other part
  that shares a row with a scroller scrolling too. A board under 290px tall (a phone browser's box with its bars
  shown) gives it its own form, a container query on the board's height (content-responsive, not a family branch):
  a wider panel, the yaku in two columns at an 18px pitch, and each score's change and total on one line while the
  panel holds four such rows (`result-foot` at least 40rem wide).
- A panel sized by its content reserves its scrollbar's gutter (`scrollbar-gutter: stable`): the overlay's auto
  track takes the panel's height before a classic scrollbar narrows it, so without the gutter the scrollbar wraps a row
  (the game end's actions) the track never grew for. The round result, its width set, keeps no gutter.
- Pages never clip the board: `.board-page` gives it the safe area, and a 10px gutter on every board but a phone's,
  whose bottom edge stays bare (a phone's board honours the side and top insets only).
  The own row stands at least its edge's depth off the bottom.
- **The live page lets a phone browser's bars collapse.** Its `.game` stands `100lvh` tall and the page sticks to the
  top, so with the bars shown the document scrolls by their height and a swipe collapses them, while the board keeps
  `100dvh` and grows into the room. In a touch browser's tab `.game` is a fixed scroll room taller and the page rests
  past that room, so it still scrolls with the bars collapsed and is not at its top, where a browser brings them back;
  an installed app and full screen keep no room and nothing scrolls. The view's `browserBars` source measures the
  difference (`100lvh` against `innerHeight`) for the board's notice, no stylesheet deciding it, and rests the page,
  again after every scroll settles. A swipe down must not reload a game: the root takes `overscroll-behavior-y: none`
  for Android Chrome, and iOS, which reloads regardless, has every downward drag refused from its first move, so there
  a swipe down cannot bring the bars back.
- **The gutter follows the family, decided once.** The board's box without the gutter, less on each edge what a
  10px gutter adds beyond the safe inset, is classified once: a phone takes no gutter and the unguttered box, any
  other family the 10px gutter on that box. Classifying the guttered board instead would flip the family at the
  threshold (desktop gutter, phone box, no gutter, desktop box). `.board-page` holds the gutter (10px, 0 around a
  phone's board) and the safe insets as registered lengths, which the directive reads in px with the padding the page
  applies, so the classification never depends on a phone's own bottom edge; a gutter change it finds
  while the observer delivers (into or out of a phone) waits a frame, since it resizes the observed board.
- Every tile's box and material is `_tile.scss`'s; each region sets `--board-tile-w`. A sideways tile (a called meld
  tile, a riichi discard) is an unturned box as long as a tile is tall with only its face turned: a turned box of a
  fractional size paints off its layout box, below its row's baseline. Flying tiles use that same
  material with animated dimensions and orientation; their grouped depth stays on an unturned wrapper, so the
  light does not rotate with the face. Native reflow stays inside its original group. An opponent's hand and melds
  isolate each tile's own depth layer below every face, never a group filter: their frame is turned (see the rivers
  below). Side hands add seam-mask layers there too: masks must never enter a shadow filter, or a separated tile
  casts a detached rectangular edge. A seam's mask stands on the tile whose edge does not fall into that seam (the
  later tile on the left, the earlier on the right), so a tile a reflow carries off keeps its whole edge attached
  instead of a mask riding with it cutting a detached sliver. An opponent's standing back draws its own edge, its top
  in the edge's colours on a pseudo-element moved down the screen (the tile itself never transformed), which casts its
  shadow. Other groups keep their shared edge and shadow. Hands and
  rivers use positional offsets: a transform creates per-tile stacking contexts that lift the side strips' seam
  masks over neighbouring faces and depth. Laid melds have no seam masks and transform their tile wrappers to
  interpolate position and size, each then its own stacking context, so where a tile's depth falls toward the tile before
  it (the top and right strips) a meld paints its tiles last to first. Reveal backs stay inside the native hand slots, absolutely placed over the hidden
  faces so they retain the hand's depth and gap masks without changing its layout.
- The rivers' shared edge and shadow come from `.board-rivers` (`_tile.scss`), the unturned layer holding all four,
  never from a turned river frame's own filter: Firefox on macOS draws a filter inside a turned frame unturned and
  clipped to its box, so no filter of a tile group may stand inside one.
- **Layers come from one scale.** Every `z-index` is a `$layers` name (`game-board/_queries.scss`), never a literal.
  `.game-board` isolates its layers from the page's. `.board-layout` and `.board-table` form no stacking context, so
  the notices and a replay's controls stand over the overlay's dim by their layers in the board's own context; an
  `isolation`, `transform`, `filter`, `opacity` or `z-index` on either would drop them under it.
