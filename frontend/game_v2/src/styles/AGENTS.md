# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`, which wins where
they disagree.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- **Sizes come from `boardGeometry` (TS).** The sizes, the geometry family, the chrome tier and every reserved
  footprint come from it, through its directive on `.game-board`; the styles place from them. Family and chrome
  branches read the emitted family and chrome, never a CSS query of the board's box. Breakpoints and viewport mixins
  are `game-board/_queries.scss`'s, which emits no CSS, so a lazy chunk's stylesheet (the replay's) can use them.
- **During the layout rethink** (`thoughts/plans/v2-board-layout-rethink.md`) a family not yet moved keeps its CSS
  solve beside the TS one, the bridge gated on the measured family, and the code may lag the spec's phone
  composition until task 10. Until then, on a phone the places beside a side strip (the notices, the decisions'
  column) still read its drawn depth, the deepest strip leaving them too narrow.
- The centre is wider than tall: its width is `--w` (half `--hx`), its height the sizing rule's side `--c` (half
  `--h`). A placement across the board offsets from `--cx` by `--hx`, one up or down from `--cy` by `--h`; a centre
  text size follows `--c`.
- Lengths are registered with `@property` (`<length>`), so each computes once to pixels; an unregistered chain grows
  with every reference until a browser drops the declaration.
- **Two script measurements**: the board's geometry directive and the notices' clamp. A choice between placements is
  made in TS, never with a length switch (`clamp(0px, x * 1000, 1px)` as a 0/1 boolean) or a `9999px` sentinel;
  content still reaches CSS as display-state custom properties (`stripStyle`, `sideStripStyle`), never fed into the
  box's sizing.
- **Places are fixed per viewport.** Badges, an opponent's full hand reach, the decisions' place, the notices' place
  and the replay's controls never move with tile counts or what a stop shows; nothing else enters a full hand's reach.
  A place beside a side strip keeps clear of the strip's deepest reach, never its depth as drawn.
- The notices never cover a tile, a plate, the centre, a decision control or a panel. A panel never covers the
  page's corner or the replay's controls.
- The own hand's tiles are the board's largest: a phone's for touch; off a phone 4/3 of the river tile (`--own-scale`),
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
  threshold (desktop gutter, phone box, no gutter, desktop box).
- Every tile's box and material is `_tile.scss`'s; each region sets `--board-tile-w`.
- The rivers' shared edge and shadow come from `.board-rivers`, the unturned layer holding all four, never from a
  turned river's own filter: Firefox on macOS draws a turned element's filter unturned and clipped to its box.
- Held-back tiles are recessed, never darkened; switch states differ by more than colour.
