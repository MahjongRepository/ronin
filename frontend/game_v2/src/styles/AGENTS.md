# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`, which wins where
they disagree.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- **Sizes come from `boardGeometry` (TS).** The sizes, the geometry family, the chrome tier and every reserved
  footprint come from it, through its directive on `.game-board`; the styles place from them. Family, chrome and
  centre branches read the emitted `data-board-family` / `data-board-chrome` / `data-board-centre`, never a CSS query
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
- **The panel's free box is the geometry's.** `boardGeometry` reserves it from the slots GameBoard fills (the corner,
  live play's or a replay's band) and the family's places; the overlay centres the panel on the board within its
  `--geo-overlay-*` insets, live and replay alike, clear of the cog. The cog reserves no other room: strips, hands and
  badges run to the board's edges under it, and it stands over them by its layer. The notices' field is reserved whether
  a notice shows or not, so no notice changes the panel's box or tiles. The panel's tile unit stays `--board-unit`, from
  that box's width and the board's height: one from `--rw` would draw a phone's result at 17px tiles where its box holds
  32px, an upright one's at 11px.
- **One source per fact.** The directive writes the sizes as `--geo-<name>` on `.game-board`; one rule
  (`_grid.scss`) maps those the styles read onto the lengths' own names on `.board-layout` and
  `.board-overlay`, inside `:where()` so it keeps (0,2,0); a name a family does not emit stays unset on its board,
  where nothing reads it. No CSS solve remains, so a board without `data-board-family` (not yet measured) hides its
  layers. A fact both sides need is TS's, emitted as a length (the chrome px, the river's footprint, the face floor,
  the latest discard's gaps); only what a container query needs stays Sass, beside a note naming its TS mirror (the
  decisions' gap and a win's rise), and the page's 10px gutter, which the page holds before the board is measured. A
  narrow desktop's notices read the left strip's drawn depth (a margin on the field's slot): past the deepest strip
  its field falls under the 7.5em floor (6.2em at 780x580, none at 1080x880), so the fixed-place rule is unmet there
  until a design choice: smaller tiles, or another place for those notices.
- **The replay fills live's slots.** GameBoard's band end (`.board-actions`, the decisions' place) holds live's
  decisions or a replay's group, its field (`.board-notices`) the notices and a replay's status; the band end's lengths
  (`--actions-*`, its room for a live row or a replay's group from the band the page fills) are the geometry's, so
  what stands beside it reads them.
  `_replay-state.scss` places no slot: it keeps the seating-on-the-centre-block rule, the controls' looks and their
  arrangement inside the band end (the moves before the options, upright the options over them, the moves in the
  switches' place where the band shares the core's corners) and the spec's panel-only exception. Upright, the band
  end's row and the own badge's lane are the geometry's (`--geo-actions-bottom`, `--own-lane`).
- **A phone's composition is its own.** `boardGeometry` solves its river tile as the largest that fits and its own
  tile on its own scale from the box (at most 1.7 river tiles, never under 36px); its band's controls float in the
  gap above the hand, its chrome follows the river tile with the control floor, and its right hand's place (the
  band row stepping in) is computed there too, never with a length switch.
- The centre is wider than tall: its width is `--w` (half `--hx`), its height the sizing rule's side `--c` (half
  `--h`). A placement across the board offsets from `--cx` by `--hx`, one up or down from `--cy` by `--h`; a centre
  text size follows `--c`.
- Lengths CSS computes are registered with `@property` (`<length>`), so each computes once to pixels; an
  unregistered chain grows with every reference until a browser drops the declaration. A bridged length is px already.
- **Two script measurements**: the board's geometry directive and the notices' clamp. A choice between placements is
  made in TS, never with a length switch (`clamp(0px, x * 1000, 1px)` as a 0/1 boolean) or a `9999px` sentinel;
  content reaches the strips through `stripLayout`, never fed into the box's sizing.
- **One strip primitive, four seats.** GameBoard's `Strip` draws every seat's hand and melds; an opponent's is a grid
  area the geometry sizes to its turned footprint (a side strip's deepest reach along its hand's room, the top one's
  stacked depth along its line), its frame turned to the seat inside (a rotation, never `writing-mode`, which leaves
  each tile's SVG unturned) from the area's corner where its hand starts. Each seat's policy is explicit
  (`STRIP_POLICY`): a side strip's melds wrap to a second line, which starts at the band (right) or ends at its room's
  end (left); the top strip's and the own row's melds keep one line and scale. Each meld is bounded only where it
  stands: by its own depth's room (the left strip's shallow meld runs past switches stepped in past its depth, a stacked
  one stops above them) and, on the top strip, by the badge only within the badge's lane, the strip's tiles one size.
  `stripLayout` (`entities/table/lib`), a pure function apart from `boardGeometry`, places an opponent's melds from what
  the strip holds and the rooms the geometry leaves it, and the directive writes them as `--<seat>-meld-<n>-*` lengths,
  with each side strip's depth as drawn (`--left-depth`, `--right-depth`); what a strip holds never reaches the
  viewport's solve. The own row's melds scale in their container (`ownMeldStyle`'s counts).
- **One river primitive, four seats.** GameBoard's `River` draws every seat's river on the tile slice's shape
  (`river-shape.ts`), its overflow an explicit per-seat policy (`RIVER_OVERFLOW`: a side river wraps a fourth row, a
  top or bottom one runs its third row on); it stays in the core's pinwheel, absolutely placed, its area a normal
  river's turned footprint with its frame turned to the seat inside (a rotation, never `writing-mode`) from the area's
  corner where the first row starts. How far a river reaches past that footprint is the geometry's: it sizes the slots
  and badges clear of it, and the styles read only the bottom river's run-on reach (`--reach-bottom-right`).
- **Places are fixed per viewport.** Badges, an opponent's full hand reach, the decisions' place, the notices' place
  and the replay's controls never move with tile counts or what a stop shows; nothing else enters a full hand's reach.
  A place beside a side strip keeps clear of the strip's deepest reach, never its depth as drawn.
- The notices never cover a tile, a plate, the centre, a decision control or a panel. A panel never covers the
  page's corner or the replay's controls.
- The own hand's tiles are the board's largest: a phone's for touch; off a phone 4/3 of the river tile,
  as large as a side seat's tile turned across the screen, every other hand and river at the river tile. No meld face
  goes under 13px wide; scaled text keeps a 10px
  floor (a safety limit, not a design size).
- A round result taller than its panel scrolls its yaku, value and score rows in place, keeping its head and the
  viewer's controls whole.
- Pages never clip the board: `.board-page` gives it the safe area, and a 10px gutter on every board but a phone's.
  No tile's edge leaves the board: the own row stands at least its edge's depth off the bottom.
- **The gutter follows the family, decided once.** The board's box without the gutter, less on each edge what a
  10px gutter adds beyond the safe inset, is classified once: a phone takes no gutter and the unguttered box, any
  other family the 10px gutter on that box. Classifying the guttered board instead would flip the family at the
  threshold (desktop gutter, phone box, no gutter, desktop box). `.board-page` holds the gutter (10px, 0 around a
  phone's board) and the safe insets as registered lengths, which the directive reads in px; a gutter change it finds
  while the observer delivers (into or out of a phone) waits a frame, since it resizes the observed board.
- Every tile's box and material is `_tile.scss`'s; each region sets `--board-tile-w`.
- The rivers' shared edge and shadow come from `.board-rivers` (`_tile.scss`), the unturned layer holding all four,
  never from a turned river frame's own filter: Firefox on macOS draws a turned element's filter unturned and clipped
  to its box.
- **Layers come from one scale.** Every `z-index` is a `$layers` name (`game-board/_queries.scss`), never a literal.
  `.game-board` isolates its layers from the page's. `.board-layout` and `.board-table` form no stacking context, so
  the notices and a replay's band end stand over the overlay's dim by their layers in the board's own context; an
  `isolation`, `transform`, `filter`, `opacity` or `z-index` on either would drop them under it.
- Held-back tiles are recessed, never darkened; switch states differ by more than colour.
