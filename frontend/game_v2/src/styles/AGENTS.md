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
  its side bars the rest of the width. The zones' layer paints the felt between `--field-left` and `--field-right`,
  the surround (`--ronin-table-surround` under its tile motif) past them, the geometry's felt (`--geo-felt-left` / `--geo-felt-right`): a
  desktop's meeting its bars' inner edges, so no bar's control stands on it (a barless desktop's edge to edge, its
  controls over the side lanes), a phone's holding its own row too; `boardGeometry` places GameBoard's
  slots (the cog, the left bar's notices' field, furiten and switches' column, a replay's controls, the
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
  the whole board, the surround past the felt, which ends a page gutter above and below the table), and the overlay, which spans the whole board for its dim, reads `--cy` shifted by the table's top.
  A height-bound board emits neither, its fallbacks the whole board.
- **The panel's free box is the geometry's.** Off a phone it is the table column, so the bars' notices stay usable
  beside a panel, and above a replay's row of controls where the band holds one, so they stay usable under it; the overlay centres the panel within its `--geo-overlay-*` insets, live and
  replay alike, over the cog where they reach it. The cog stands at the right bar's top, in the board's top-right
  corner where the bar is narrower than its target and a gap. No notice changes the panel's box or tiles: the notices
  and a replay's status reserve nothing and stand over the panel by their layer where it reaches them. A phone's panel takes equal side gaps and stands
  centred (a replay's clear of its moves, by the geometry's `overlay-right`), whether or not a notice shows: its notices
  and a replay's status keep their field in the left bar and stand over the panel by their layer, reserving nothing.
  The panel's tile unit stays `--board-unit`, from
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
  floor; a desktop's toasts' the board's share, never under 14px, over a panel too.
- **Live decisions stand in one cluster; the bars hold the rest.** Off a phone live's decisions (`.board-actions`)
  stand in a band along the own row's top: from the bottom river's start (the centre's left edge, the toasts
  standing in the corner it leaves) to short of the right strip's lane, under the centre and the right river's first tile and over the own
  row's melds' rise, in as many rows of `--decision-h` controls as its width needs. The own river, the plates there
  and, on a short window, the right river's first tiles may lie under it: the cluster stands over them (its layer,
  solid controls with `--action-lift`), since no decision's source lies in the own river, and no table width or
  stack row is reserved for it. Its controls, the offers'
  (`.decision-controls__upper`, a box of none of its own there) and the band's (the pass, then the timer
  `--actions-band-w` wide, as one piece), wrap up from its bottom right, growing left along the row first, every
  label at the geometry's `--action-text`. A desktop's notices stand apart from the field as toasts of up to two lines in the core's
  bottom-left corner, under the left river's longest reach and over the own row (`toasts`), stacked down from its
  top, cut short with an ellipsis past their second line (the whole in the notice's title, the cut one opening the
  sheet), the last ones left out where the felt is short (the last shown its "+N"), with or without a panel (`toast-board`,
  every desktop board), over the panel where it reaches them; a replay's status stands apart in the left bar under
  the dora, past the bar's width over the table where it needs to. Nothing is reserved for either. A replay's moves and options stand in one row along that band's foot from its
  start, over the bottom river's last row (a replay is read stepping past it), at the control floor or larger and off
  the own plate's pill; where the band holds no such row (a small window) they take the right bar's foot instead, in one
  column or two; in two, each move back stands beside its move on and autoplay spans both under them. The form is
  the geometry's (`data-board-replay`), never a CSS query. Nothing but live's decisions or
  a replay's row stands between the bottom river and the own row. On a phone
  live's decisions stand in a band along the own row's top too, from short of the left strip's lane to short of the
  right one's, under the centre and the right river (or from the centre's left edge where its bottom row cannot pass
  under the left river's longest reach), the same cluster in 40px rows `$phone-band-row-gap` apart, inside the felt; the right rail
  holds the cog and a replay's column at its foot (two columns at the right bar's foot above the own row where a rail
  a control wide holds no column), the left rail the switches at its foot by the screen's edge, as the geometry's form
  (`data-board-switches`: the two-by-two `block` or the `letters` column), the left bar the counters at the felt's
  corner and the notices, over the felt's edge beside the left strip: neither reserves room for the decisions, and the phone solve
  takes no tile whose band would not hold the widest prompt's rows (`$phone-band-row-gap` mirrored in TS).
  `_replay-state.scss` places no slot.
- **One composition, two profiles.** Off a phone there is one desktop family: the river tile from
  the vertical stack, the own tile from the width a full hand between the side lanes keeps, 1.2 to 1.45 river
  tiles; no side strip's tile stands over the own row's span. A phone keeps the composition with its own profile: `boardGeometry`
  solves its river and own tiles together from the box (the spec's sizing rule), its own row spans its felt under
  both lanes (in the shortest browser boxes, where above it the lanes cannot hold three kans or the decisions' band
  the widest prompt, between them, the lanes and bars running down beside it); a family difference is the geometry's, never a
  length switch.
- The centre is a rectangle in every family, `--c`/`--h` its height and `--w`/`--hx` its width: off a phone six river
  tiles wide by 4.5 tall, on a phone the height left over the own row. Its score rows and their inset follow the
  shorter of the two; the round and counts follow `--c` within the room `--w` leaves. The geometry fits the centre and the rivers together, at the spec's minimums (Proportions).
- Lengths CSS computes are registered with `@property` (`<length>`), so each computes once to pixels; an
  unregistered chain grows with every reference until a browser drops the declaration. A bridged length is px already.
- **The tilted pieces.** `.board-surface`, inside `.board-table`, as tall as the board and standing at its top, holds
  the rivers, the centre, the opponents' strips and the counters; each takes the `matrix3d()` `tableView`
  (`entities/table/lib/table-camera.ts`) emits for it (`--geo-camera-*`, the piece's move on the plane, then the one
  camera's homography) from its top left corner (the counters take an upright `matrix()`, a desktop's from their tilted far edge, a phone's at their flat corner), and the plane's lengths, which the directive writes on the surface itself,
  so inside it every `--geo-*` is the plane's. TS owns the projection, so the flat overlays (`--geo-shown-*`: the
  plates, calls and the felt's seams) and the checks land exactly on what the browser paints. The surface makes no
  stacking context and clips nothing; the rivers' shared edge filter stays on the unturned `.board-rivers`. Firefox
  paints the edges inside a flat `matrix3d` piece unsmoothed, so the seams between river tiles step 1px at a time; a
  river there takes a neutral `blur(0.01px)` on its own host, above its turned frame, which sends it through a path
  that smooths them. `preserve-3d` smooths them too but makes Firefox drop the shared shadow around a tile hidden as
  it is laid, so it is not used. iOS Safari leaves a tilted layer's outer edges unsmoothed, so a tile edge on a
  piece's box steps a pixel at a time; every `matrix3d` piece (rivers, opponents' strips) and each motion flight
  therefore stands in a transparent `$tilted-piece-edge-gutter` border, a piece's offset by a negative margin and its
  `transform-origin` at the border's inner corner, so the camera still acts from the inner box's corner, which motion
  snapshots read through `clientLeft`/`clientTop`. The gate
  measures laid sizes and floors with the pieces' transforms off (`measurePlane`) and the shown faces and gaps with
  them on.
- **The top hand stands off the plane.** The top seat's hand is not in its strip's tilted piece but in a sibling host,
  `.board-strip--top-hand`, on the same grid area with the same turned frame, taking a flat `matrix()`
  (`--geo-camera-top-hand`) that stands its foot where the strip's camera shows it, so its tiles stand upright
  instead of leaning with the perspective. Its height follows the camera only up to a fixed shown aspect
  of the back, so a steep camera never stretches the backs; a revealed hand (`.board-strip--revealed`) takes
  `--geo-camera-top-hand-revealed`, the same foot and width with its owner's edge where the camera shows it, since its
  faces lie on the table. The host stays an unturned child of the
  strips' wrapper (`.board-strips`, a grid of the surface's tracks) with no `matrix3d` above it: the wrapper casts its
  shadow with the strips', motion snapshots read its tiles as
  their boxes, and `measurePlane`'s reset covers it. Nesting it in the tilted strip would turn its shadow with the
  frame and give snapshots a false taper.
- **Layout measurements**: the board's geometry directive and the notices' clamp. Motion snapshots only measure
  existing tile positions for temporary copies; they never feed the layout solve. A choice between placements is
  made in TS, never with a length switch (`clamp(0px, x * 1000, 1px)` as a 0/1 boolean) or a `9999px` sentinel;
  content reaches the strips through `stripLayout`, never fed into the box's sizing.
- **One strip primitive, four seats.** GameBoard's `Strip` draws every seat's hand and melds; an opponent's is a grid
  area the geometry sizes to its turned footprint (a side lane's reserve along its hand's room, the top one's
  stacked depth along its line), its frame turned to the seat inside (a rotation, never `writing-mode`, which leaves
  each tile's SVG unturned) from the area's corner where its line starts, a side hand at `--<seat>-hand-along`. Every seat keeps its melds in one line to its owner's right,
  oldest at the far end; side melds never wrap into parallel columns. `stripLayout` scales all melds
  together to fit, using their actual footprints to clear the own row. `stripLayout` (`entities/table/lib`) stays separate from
  `boardGeometry`. Contents never enter the viewport's solve. The own row's melds take `--own-meld-w` from `ownMeldTile` over the melds' structure, never from the hand's current width. No tile size, hand start or laid meld's place may follow transient content (a draw, a discard, an offer): a stylesheet never fits tiles to the room content leaves.
- **One river primitive, four seats.** GameBoard's `River` draws every seat's river on the tile slice's shape
  (`river-shape.ts`), its overflow an explicit per-seat policy (`RIVER_OVERFLOW`: a side river wraps a fourth row, a
  top or bottom one runs its third row on); it stays in the core's pinwheel, absolutely placed, its area a normal
  river's turned footprint with its frame turned to the seat inside (a rotation, never `writing-mode`) from the area's
  corner where the first row starts. Layouts are designed and checked for rivers of up to twenty discards: the
  geometry reserves a top or bottom river's third row run on to eight, a sideways riichi tile counted, when placing
  slots and plates. A river of 21 or more may run under other elements (the decisions, plates, a strip); nothing
  reserves room for it and no story or check builds one.
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
  The own row stands at least its edge's depth, or its standing body's overhang, off the bottom; the overhang is
  reserved in whole pixels, so on a phone the body's foot may be clipped by up to 1px at the board's bottom edge.
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
- Every tile's box is `_tile.scss`'s; each region sets `--board-tile-w`. Its material is a generated body
  (`entities/tile/lib/tile-body.ts`): `Tile` and `TileBack` pick it from the tile's lay and its seat's turn
  (`tileBody`), draw it as an `<svg>` centred on the 4:3 box with its edge running past the box toward the screen's
  bottom, and turn it back by the seat's frame turn (`--body-turn`), so a body is always drawn upright on the
  screen. The own hand's standing face tiles draw `StandingTile`'s standing body instead: their 4:3 box stays the
  layout and tap target, the body running past its bottom (no pointer events), the focus ring on the body. A sideways
  tile (a called meld tile, a riichi discard) is an unturned box as long as a tile is tall: a turned box of a
  fractional size paints off its layout box, below its row's baseline.
- **Paint order replaces masks.** A body nearer the screen's bottom paints over the edge of the one above it. Where
  DOM order runs up the screen the components set the slots' `z-index` from the seat's turn (the top river's rows,
  the right river's and the right strip's lines); an added kan renders its two tiles in paint order; the right
  strip's hand stands over its melds and its melds paint from the far end down (`_tile.scss`). Nothing masks a
  seam. A side strip's back whose end the next tile covers takes the body that draws no end (`Hand` picks it per
  slot); it also holds the end-drawing body, hidden, which shows while the reflow
  player marks its slot `hand-tile--parted`: while the slot covering it moves differently (one moving, the other
  still, or a different offset or timing), from a move's start, its delay included, until its last move ends.
  Marking the whole hand would draw every covered end for the slide.
- **One cast shadow per group.** Tiles lying together cast one drop shadow from an unturned ancestor: the rivers'
  from `.board-rivers`, the opponents' from `.board-strips`, never from a turned frame (Firefox on macOS draws a
  filter inside one unturned and clipped to its box) nor from a `matrix3d` piece (Chrome rasterizes a filtered 3D
  piece at 1x, blurring it on a 2x screen). A tile alone casts its own; a hand that takes input
  casts one per button. Flying tiles clone their destination's body from take-off, upright on the screen whatever
  the flight's angle, and cast one shadow on their image. Native reflow stays inside its original group; reveal
  backs stay inside the native hand slots, absolutely placed over the hidden faces.
- **Layers come from one scale.** Every `z-index` is a `$layers` name (`game-board/_queries.scss`), never a literal,
  but a tile group's paint order: ordinals counted from the seat's turn (the slots' inline `z-index`, the right
  strip's areas and melds), which stay inside the group's stacking context and never meet a layer.
  The scale follows the spec's tiers (Principles, *Three tiers*): the plates take `furniture` and stand first in
  `.board-table`, so every tile area after them, positioned, paints over them; a task element takes a layer over
  every table piece it may stand on. Never raise a furniture or table element's layer to keep it in view.
  `.game-board` isolates its layers from the page's. `.board-layout` and `.board-table` form no stacking context, so
  the notices and a replay's controls stand over the overlay's dim by their layers in the board's own context; an
  `isolation`, `transform`, `filter`, `opacity` or `z-index` on either would drop them under it.
