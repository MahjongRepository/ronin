# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- **Sizes come from `boardGeometry` (TS).** It reaches `.game-board` through its directive
  (`entities/table/ui/board-geometry-directive.ts`); its chrome lengths reach CSS as px, bridged in
  `game-board/_grid.scss`, and a new chrome length comes from it, never a per-tier literal.
  Family, chrome, switch-form and arrangement branches read the emitted `data-board-family` / `data-board-chrome` /
  `data-board-switches` / `data-board-arrangement` (a desktop's only), never a CSS query
  of the board's box (nor
  `@container style()`, which Safari 16.4 lacks); container queries serve only content-responsive rules. The
  family and chrome mixins are `game-board/_queries.scss`'s, which emits no CSS, so a lazy chunk's stylesheet (the
  replay's) can use them: a nested rule's selector takes the attribute inside `:where()` on its board compound, or
  behind a `:where(.game-board)` where it names none, keeping its specificity and place; a top-level block names the
  board itself.
- **The shell is a grid from the geometry's tracks; the pinwheel is local.** `boardGeometry` places GameBoard's
  slots as named grid areas and emits the templates (`--geo-shell-columns` / `--geo-shell-rows`); each slot takes its
  `grid-area`. A slot's place is never a CSS formula: what its contents read (`--actions-*`, `--switch-*`, the
  notices' field and toasts' heights, which the notices' clamp reads as `max-height`) comes from the geometry too. The
  core's pinwheel, the nameplates, the counters and a replay's status over a smaller board's panel stand absolutely
  over the grid, by the geometry's lengths.
- **A width-bound desktop's table is a frame of its own.** Where the board is taller than its table needs,
  `.board-layout` stands at `--geo-table-top`, `--geo-table-h` tall, and every length, track and slot is in that
  frame; a layer that spans the whole board (the zones', the overlay's dim) adds the table's top, as the overlay's
  `--cy` does (`game-board/_grid.scss`).
- **The panel's free box is the geometry's** (`--geo-overlay-*` insets; where it stands is the spec's Panels). The
  panel's tile unit stays `--board-unit`, from that box's width and the board's height: one from `--rw` would draw a
  phone's result at 17px tiles where its box holds 32px.
- **One source per fact.** The directive writes the sizes as `--geo-<name>` on `.game-board`; one rule (`_grid.scss`)
  maps those the styles read onto the lengths' own names on `.board-layout`, `.board-overlay` and `.board-surface`, inside `:where()` so
  it keeps (0,2,0); a name a family does not emit stays unset on its board, where nothing reads it. There is no CSS solve,
  so a board without `data-board-family` (not yet measured) hides its layers. A fact both sides need is TS's,
  emitted as a length (the chrome px, the river's footprint, the latest discard's gaps); only what a
  container query needs stays Sass, along with the
  page's 10px gutter, which the page holds before the board is measured.
- **Live decisions stand in one cluster; the bars hold the rest** (where each stands is the spec's Decisions, Notices
  and Replay). The cluster (`.board-actions`) stands over the own river, the plates and a short window's right-river
  tiles on its layer, with solid controls and `--action-lift`; no table width or stack row is reserved for it. Its
  sizes (`--decision-h`, `--action-text`, widths and gaps) and the replay controls' form (`data-board-replay`) are the
  geometry's, never a CSS query. Nothing but live's decisions or a replay's row stands between the bottom river and
  the own row. `_replay-state.scss` places no slot.
- Lengths CSS computes are registered with `@property` (`<length>`), so each computes once to pixels; an
  unregistered chain grows with every reference until a browser drops the declaration. A bridged length is px already.
- **The table's pieces are flat.** `.board-surface`, inside `.board-table`, as tall as the board and standing at its
  top, holds the rivers, the centre, the opponents' strips and the counters; each takes the transform `tableView`
  (`entities/table/lib/table-view.ts`) emits for it (`--geo-camera-*`) from its top left corner, which only moves it
  to the table's top, and the lengths the directive writes on the surface itself. So every piece is shown as laid: the
  overlays (`--geo-shown-*`: the calls and the felt's fields), motion snapshots and the checks read the boxes the
  browser paints, with no projection to take back. A piece's transform is one static value per resize, never per
  frame. The surface makes no stacking context and clips nothing. Its full-board
  layers (the surface, the rivers, the strips) pass the pointer through, so the plates under them take presses; a
  piece that takes the pointer opts back in (the centre, each strip).
- **The top hand stands in its own host.** The top seat's hand is not in its strip's piece but in
  `.board-strip--top-hand`, a sibling on the same grid area, stood on its foot by a flat `matrix()` (`topHandValues`
  in `table-view.ts`). It stays an unturned child of `.board-strips`, so it casts its shadow with the strips' and
  motion snapshots read its tiles as their boxes; nested in the strip's turned frame, its shadow would turn with the
  frame.
- **Layout measurements**: the board's geometry directive and the notices' clamp. Motion snapshots only measure
  existing tile positions for temporary copies; they never feed the layout solve. A choice between placements is
  made in TS, never with a length switch (`clamp(0px, x * 1000, 1px)` as a 0/1 boolean) or a `9999px` sentinel;
  content reaches the strips through `stripLayout`, never fed into the box's sizing.
- **One strip primitive, four seats.** GameBoard's `Strip` draws every seat's hand and melds; an opponent's is a grid
  area the geometry sizes to its turned footprint (a side lane's reserve along its hand's room, the top one's
  stacked depth along its line), its frame turned to the seat inside (a rotation, never `writing-mode`, which leaves
  each tile's SVG unturned) from the area's corner where its line starts, a side hand at `--<seat>-hand-along`.
  `stripLayout` (`entities/table/lib`) stays separate from `boardGeometry`. Contents never enter the viewport's
  solve. The own row's melds take `--own-meld-w` from `ownMeldTile` over the melds' structure, never from the hand's
  current width. A stylesheet never fits tiles to the room content leaves.
- **One river primitive, four seats.** GameBoard's `River` draws every seat's river on the tile slice's shape
  (`river-shape.ts`), its overflow an explicit per-seat policy (`RIVER_OVERFLOW`, `entities/table/ui/game-board.ts`);
  it stays in the core's pinwheel, absolutely placed, its area a normal river's turned footprint with its frame turned
  to the seat inside (a rotation, never `writing-mode`) from the area's corner where the first row starts.
- **Places are fixed per viewport.** Badges, an opponent's full hand reach, the decisions' place, the notices' place
  and the replay's controls never move with tile counts or what a stop shows; nothing else enters a full hand's reach.
  A place beside a side strip keeps clear of the strip's deepest reach, never its depth as drawn.
- A round result fits its panel whole at every supported size, and its sizes never follow the shown page or the hand
  (the spec's Panels and Round result). Its compact form (`$result-compact-height`, `game-board/_queries.scss`) and
  large type (`$result-large-height` with the `round-result` panel at `$result-large-panel-width`) are container
  queries on the board's height and the panel's width, content-responsive and not family branches; the panel's width
  is the table column's, not the board's.
- A panel sized by its content reserves its scrollbar's gutter (`scrollbar-gutter: stable`): the overlay's auto
  track takes the panel's height before a classic scrollbar narrows it, so without the gutter the scrollbar wraps a row
  (the game end's actions) the track never grew for. The round result, its width set, keeps no gutter.
- Pages never clip the board: `.board-page` (`game-board/_pages.scss`) gives it the safe area and the gutter.
- **The live page and the replay let a phone browser's bars collapse** (`game-board/_pages.scss`; `index.ts`'s
  `keepPageRestedPastItsTop`). In a touch browser's tab the page rests part way down a taller scroll room
  (`--page-rest`, set by the stylesheet alone): off its top, where a browser brings the bars back, and with more room
  below than the bars are tall, since Safari snaps them back when a drag reaches the page's end with the bars half
  collapsed. The board's notice comes from the live view's `browserBars` measure, never from a stylesheet. A swipe
  down must not reload a game: `overscroll-behavior-y: none` stops it on Android Chrome; iOS reloads regardless, so
  there every downward drag is refused from its first move and a swipe down cannot bring the bars back.
- **The gutter follows the family, decided once** (the spec's sizing rule): classify from the unguttered box less
  what the 10px gutter would add beyond the safe inset, never from the guttered board, which would flip the family at
  the threshold (desktop gutter, phone box, no gutter, desktop box). `.board-page` holds the gutter and the safe insets
  as registered lengths the directive reads in px (`board-geometry-directive.ts`).
- Every tile's box is `_tile.scss`'s base `.tile` rule; each region sets `--board-tile-w`. A lying tile's box is its
  slot, foreshortened by the per-axis shares its component sets inline (`--slot-across-share`,
  `--slot-down-share`), never by a board custom property, so a lying tile off the board (a result, a decision chip, a
  storybook) is the board's. Its body (`entities/tile/lib/tile-body.ts`, picked by `tileBody`) is drawn as an `<svg>`
  on the slot and turned back by `--body-turn`; the edge is never part of the slot. A sideways tile (a called meld
  tile, a riichi discard) is an unturned box as long as a tile is tall: a turned box of a fractional size paints off
  its layout box, below its row's baseline.
- **Paint order replaces masks; nothing masks a seam** (the order is the spec's, Principles). Where DOM order runs
  up the screen the components set the slots' `z-index` from the seat's turn; the right strip's order is
  `_tile.scss`'s. A side strip's covered back takes the body that draws no end and holds the end-drawing one hidden,
  shown while the reflow player marks that slot `hand-tile--parted`; mark only the parted slot, since marking the
  whole hand would draw every covered end for the slide.
- **One cast shadow per group.** Tiles lying together cast one drop shadow from an unturned ancestor: the rivers'
  from `.board-rivers`, the opponents' from `.board-strips`, never from a turned frame (Firefox on macOS draws a
  filter inside one unturned and clipped to its box) nor from a piece the view seam transforms (Chrome rasterizes a
  filtered 3D-transformed piece at 1x, blurring it on a 2x screen). A tile alone casts its own; a hand that takes input
  casts one per button. Flying tiles are shadowless ghost copies of their destination, its body, size and
  turn set once on the image (`--motion-*`), upright on the screen; only their `translate` animates. Native reflow
  stays inside its original group; a hand slot's reflow animates `translate` alone, never `transform`, because the own
  hand's lifts use `transform`, and no `z-index` or `filter`; reveal backs stay inside the native hand slots,
  absolutely placed over the hidden faces.
- **Layers come from one scale.** Every `z-index` is a `$layers` name (`game-board/_queries.scss`), never a literal,
  but a tile group's paint order: ordinals counted from the seat's turn (the slots' inline `z-index`, the right
  strip's areas and melds), which stay inside the group's stacking context and never meet a layer.
  The scale follows the spec's tiers (Principles, *Three tiers*): the plates take `furniture` and stand first in
  `.board-table`, so every tile area after them, positioned, paints over them; a task element takes a layer over
  every table piece it may stand on. Never raise a furniture or table element's layer to keep it in view.
  `.game-board` isolates its layers from the page's. `.board-layout` and `.board-table` form no stacking context, so
  the notices and a replay's controls stand over the overlay's dim by their layers in the board's own context; an
  `isolation`, `transform`, `filter`, `opacity` or `z-index` on either would drop them under it. A callout stands
  over every layer but what the player opens (`open`, `sheet`) and the page's, the panel and notices included, and
  its entrance grows from its edge toward its seat (a bottom one from its centre), so even its largest frame stays on
  the board; `.board-page` clips, so nothing floating on the board can scroll the page and resize the board.
