# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`, which wins where
they disagree.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- **Sizes come from `boardGeometry` (TS).** The sizes, the geometry family, the chrome tier and every reserved
  footprint come from it, through its directive on `.game-board`; the styles place from them. Family and chrome
  branches read the emitted `data-board-family` / `data-board-chrome`, never a CSS query of the board's box (nor
  `@container style()`, which Safari 16.4 lacks); container queries remain only for content-responsive rules. The
  family and chrome mixins are `game-board/_queries.scss`'s, which emits no CSS, so a lazy chunk's stylesheet (the
  replay's) can use them: a nested rule's selector takes the attribute inside `:where()` on its board compound, or
  behind a `:where(.game-board)` where it names none, keeping its specificity and place; a top-level block names the
  board itself.
- **The panel's free box is the geometry's.** `boardGeometry` reserves it from the slots GameBoard fills (the corner,
  live play's or a replay's band) and the family's places; the overlay centres the panel on the board within its
  `--geo-overlay-*` insets, live and replay alike. The notices' field is reserved whether a notice shows or not, so no
  notice changes the panel's box or tiles. The panel's tile unit stays `--board-unit`, from that box's width and the
  board's height: one from `--rw` would draw a phone's result at 17px tiles where its box holds 32px, an upright one's
  at 11px.
- **During the layout rethink** (`thoughts/plans/v2-board-layout-rethink.md`) the directive writes the sizes as
  `--geo-<name>` on `.game-board`; the bridge rules after every family block (`_grid.scss`) map them onto the lengths'
  own names on `.board-layout` and `.board-overlay`, gated on `data-board-family` inside `:where()` so they keep
  (0,2,0) and the lazy replay's overrides still win. There are three: one for the desktop, short desktop and phone,
  one for the phone's chrome and right hand alone, and one for upright; a name a rule maps that one of its families
  does not emit stays unset on that family's board, where nothing reads it. No CSS solve remains, so a board without
  `data-board-family` (not yet measured) hides its layers. A literal both sides need is a TS constant emitted as a
  `--geo-*` length (the latest discard's gaps); one still in SCSS stays beside a note naming its TS mirror. Until
  task 16 a narrow desktop's notices still read the side strip's drawn depth, the deepest strip leaving them too
  narrow.
- **A phone's composition is its own.** `boardGeometry` solves its river tile as the largest that fits and its own
  tile on its own scale from the box (at most 1.7 river tiles, never under 36px); its band's controls float in the
  gap above the hand, its chrome follows the river tile with the control floor, and its right hand's place (the
  corner and the band row stepping in) is computed there too, never with a length switch.
- The centre is wider than tall: its width is `--w` (half `--hx`), its height the sizing rule's side `--c` (half
  `--h`). A placement across the board offsets from `--cx` by `--hx`, one up or down from `--cy` by `--h`; a centre
  text size follows `--c`.
- Lengths CSS computes are registered with `@property` (`<length>`), so each computes once to pixels; an
  unregistered chain grows with every reference until a browser drops the declaration. A bridged length is px already.
- **Two script measurements**: the board's geometry directive and the notices' clamp. A choice between placements is
  made in TS, never with a length switch (`clamp(0px, x * 1000, 1px)` as a 0/1 boolean) or a `9999px` sentinel;
  content still reaches CSS as display-state custom properties (`stripStyle`, `sideStripStyle`), never fed into the
  box's sizing.
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
- The rivers' shared edge and shadow come from `.board-rivers`, the unturned layer holding all four, never from a
  turned river's own filter: Firefox on macOS draws a turned element's filter unturned and clipped to its box.
- Held-back tiles are recessed, never darkened; switch states differ by more than colour.
