# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) meet `docs/game-client-look.md`, which wins where
they disagree.

- **The board sizes itself from its own box.** `.game-board` is a size container named `game-board`; every length
  derives from its box (container query units), never the viewport. A page that gives it a box decides its size.
- The sizing rule lives in `game-board/_grid.scss` alone. Breakpoints and viewport mixins are
  `game-board/_queries.scss`'s, which emits no CSS, so a lazy chunk's stylesheet (the replay's) can use them.
- Lengths are registered with `@property` (`<length>`), so each computes once to pixels; an unregistered chain grows
  with every reference until a browser drops the declaration.
- **No script measurement** (except the notices' clamp). Content that changes a placement reaches CSS as custom
  properties from the display state (`stripStyle`, `sideStripStyle`). A choice between two placements is a length
  switch, `clamp(0px, x * 1000, 1px)`, from viewport lengths, never from what a seat holds.
- **Places are fixed per viewport.** Badges, an opponent's full hand reach, the decisions' place, the notices' place
  and the replay's controls never move with tile counts or what a stop shows; nothing else enters a full hand's reach.
- The notices never cover a tile, a plate, the centre, a decision control or a panel. A panel never covers the
  page's corner or the replay's controls.
- The own hand's tiles are always the board's largest; no meld face goes under 13px wide; scaled text keeps a 10px
  floor (a safety limit, not a design size).
- A round result taller than its panel scrolls its yaku, value and score rows in place, keeping its head and the
  viewer's controls whole.
- Pages never clip the board: `.board-page` gives it the safe area exactly.
- Every tile's box and material is `_tile.scss`'s; each region sets `--board-tile-w`.
- Held-back tiles are recessed, never darkened; switch states differ by more than colour.
