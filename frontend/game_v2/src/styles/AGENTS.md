# Board layout

How the board's stylesheets (`game-board/`, the partials beside it) place the table. The board's target is
`docs/game-client-look.md`, which wins where it and this file disagree; what follows is how the code meets it.

## Sizing

- **The board sizes itself from its own box.** `.game-board` is a size container and every length in it derives from
  its box (container query units), never the viewport, so a page that gives it a box (`.board-page`) decides its size
  alone. The spec's sizing rule (`docs/game-client-look.md`, Proportions) lives in `game-board/_grid.scss` alone, as
  custom properties on the board's layout and its overlay: the own tile (36x48 under 520px high, else
  min(5cqw, 10cqh), capped by a full hand's row beside its badge's and furiten's slots), the river tile, the core, the
  centre and every place derived from them (the rivers' capacity reach, the foreground band, a badge's place); its
  breakpoints, viewport mixins and the side strips' depth as drawn are `game-board/_queries.scss`'s, which emits no
  CSS, so a lazy chunk's stylesheet (the replay's) uses them without repeating the board's rules.
- Its lengths are registered (`@property`, `<length>`), so each computes once to pixels where it is set: an
  unregistered chain grows with every reference until a browser drops the declaration.
- A desktop's core also stays above the foreground band's controls and below the top strip's slot; a short desktop
  (`short-desktop-board`: under 760px high, at least 1100px wide, such as 1366x657) shares the band's lower corners as
  a phone does instead; an upright board takes the desktop rule, its core bounded by the width left beside two lines
  of side melds. A choice the rule makes between two placements is a length selected by `clamp(0px, x * 1000, 1px)`
  from the viewport's lengths (a full hand's reach, the band's top), never from what a seat holds.
- The perimeter's chrome (badges, counters, the page's corner, callouts) takes a phone's size on a phone, upright and
  on a desktop board under 1100px wide, whose geometry stays the desktop's, and a step larger on a board of at least
  2000x1200; the top strip's hand starts right of the counters however narrow the board.
- Nothing is measured in script (but the notices' clamp, `entities/client/AGENTS.md`): what content changes a
  placement (a strip's hand and meld lengths, in tile widths) the board hands its stylesheet as custom properties from
  the display state (`stripStyle`). The own hand's tiles are always the board's largest. Every tile's box (its 3:4
  from `--tile-w`, the room around the glyph, the corners) is `_tile.scss`'s; each region sets `--board-tile-w`. A
  round result taller than its panel scrolls under its foot, which keeps the scores, the primary button and its
  countdown at the panel's bottom.
- The board's container is named `game-board` and its viewport mixins query it by name, so a container inside the
  board never answers them. Text the board scales keeps a 10px floor, a safety limit, never the size to design to.
- **Pages never clip the board.** `.board-page` gives it a definite box, the safe area exactly (sized with `dvh` and
  the theme's `--ronin-safe-*`, which a test can set; the table's surface runs on under the insets). A storybook's
  switches always lie below the board, so its board is the live game's box (36x48 own tile at 667x375) and the page
  scrolls to them. The replay's page is the board alone, the live game's box.

## The live page's corner and panels

- The page's controls sit in the board's top-right corner, so a phone gives the board its whole width. A panel over
  the board leaves the corner clear (`game-board/_overlay.scss`, the spec's Panels): a desktop caps the corner to a
  reserve the overlay keeps free on both sides of a centred panel; a narrow desktop (narrower than
  `$small-chrome-width`) has the height but not the width, so its panel stands under the corner's height, between the
  side strips (past the left river's reach while notices show); a short board keeps the reserve on the corner's side
  alone and tops the panel; the overlay's tiles size from the width left; an upright board's panel stands under the
  corner's height, and above the foreground while notices show (they take the reserve under the right strip's end).
- The notices lie in the table's own area, never over a tile, a plate, the centre, a decision control or the panel,
  however long they stay. Their place is the left field under the left badge, outside every river's capacity and past
  the left strip as drawn (its second meld line included, from the lengths `sideStripStyle` hands the table), above a
  panel's dimming; what a page shows in their place lies under them (a replay's status); a desktop panel over the
  board then starts past the left river's reach, and over a short or upright board's panel they move to the reserve
  under the right strip's end, but under a modal panel (their sheet, the leave question) they stay put, hidden, their
  clamp kept.

## The table

What the code keeps that the spec (Composition, Elements) does not say:

- Each seat's river and strip is laid in its own frame (left to right from its seat, rows away from the centre, a
  strip's tiles standing on the frame's line toward the seat's edge) and turned into place about the frame's corner,
  so a seat's tiles face it and an added kan's stack lies on its centre-facing side at every seat. A river's tiles
  touch; the pinwheel's gaps (0.3 of a river tile, rounded) part the rivers from each other and the centre at every
  capacity. A side river wraps past its third row into a fourth (`Discards`' `wrap`), a top or bottom one runs its
  third on (`run-on`).
- An opponent's concealed hand is at the river tile's size, its drawn tile 0.15 of one apart (`--dg`), and its full
  reach (`--full-reach`, fourteen tiles and that gap) has a fixed place per viewport that nothing else enters: the left
  hand runs down from below the counters and the play switches step in past its depth (`--switches-clear`) where it
  would meet them; the right hand's origin (`--right-origin`) is the band's top under the corner, else the top margin
  with the corner stepped in (`--corner-shift`, which the top badge's room and a panel's corner reserve also take),
  else under the corner across the band, whose phone row then ends before it (`--band-shift`, which a short board's
  notices over a panel follow). The choice asks whether the hand from that origin enters the band row's height (its
  box starts at the band's top), with half a pixel's tolerance, so the floor's height keeps two pixels of margin
  whatever the slots' widths. With the corner stepped in, the strip's melds may rise to the top margin only while none
  is deeper than a sideways tile (an added kan's stack would meet the corner). A board without the page's corner (a
  replay's, the board storybook's) reserves none and steps nothing. The top hand stands centred, short of a badge's
  width (`--top-badge-w`) before the corner and right of the counters.
- A side strip's melds take its line while they fit and its oldest the second line inside it, from the foreground
  band toward its badge, scaled to end before the badge: each meld's place is chosen in CSS from the units the board
  hands it (`--mu-k`), never by measuring. The top strip keeps one line and scales its melds down, above the top river
  and the side badges and right of the counters; the own melds keep 1.2 river tiles, scaled down to end before the
  board's edge (their area is a size container, from the meld units the board hands the own row). No meld face goes
  under 13px wide.
- A badge's place is fixed per viewport and never reads a tile count: the side badges stand clear of the deepest a
  strip's first line can be (two river tiles), and below the top river's capacity row wherever they would meet it
  (always on a phone), the right one level with the left unless that puts it beside the right river's rows (the top
  river's row never reaches that side); a side badge beside its river's rows ends before its reach. The own badge has
  its slot at the start of the own row, whose hand starts where a full hand's would, whatever it holds. Badges are the
  plates' one shape; a long name is shortened in the middle so its end shows; an upright board shows the wind and
  marks alone, its name in the label.
- The pooled counters (top-left) hold the dora and the honba and riichi counts as icon and number; the centre holds
  the round, the wall's count, each seat's wind and score in a pinwheel row on its side, its riichi stick inside the
  edge, the turn's bar on the edge, and while a badge's differences show, whose: a label in the round's place, "vs"
  over the seat's whole name where it fits that line, else its wind: the line clips a column of the name and the
  wind, which moves up by the name's own height once the name wraps (no script measures it).
- The latest discard (`lastDiscardSeat`, `entities/table/AGENTS.md`) is ringed with a notch on its far side, in its
  river's frame, in the table's neutral latest colour; a claimed tile has left the river. A chankan offer's kan is
  ringed whole in its meld (`meld--source`) until the offer resolves.
- The decisions' place (`_decision-controls.scss`): on a desktop one row in the foreground band, from past the play
  switches' slot (`--switches-left`/`--switches-right`, on the band's side away from the decisions) to the own row's
  right end, the timer's fixed slot (`--timer-w`, a caption line over the digits: Time up, Sent, Bank) last; a row too
  narrow for its controls (a narrow desktop's) wraps the higher-ranked above the band's control and the timer, and four
  or more under 800px shed their tile previews and spare width. A short desktop's row starts past the bottom and right
  rivers' capacity reach and always stacks the higher-ranked above the band's control and the timer, padded clear of
  the right strip as drawn (`--upper-clear`, from `--right-depth`); the band's control wraps above the timer where the
  row cannot hold both, padded the same. A control's tiles stay inside the band's row room (`--row-room`: the
  control's height and the band's slack less the 4px kept from a tile), so the river's growth on a large board never
  brings a control within reach of the bottom river.
- On a phone the lowest-ranked control that is neither a win, a choice of tiles nor a call's first step takes the band
  row beside the timer (the riichi toggle among them), starting past the own river's capacity reach; the rest stack
  upward, right-aligned, between the right river's capacity reach and the right strip as drawn (its second meld line
  counted, from the per-meld units `rightStripStyle` hands the stylesheet), a win or a choice across the column, and
  pair up, shedding their tile previews, where the column (a size container, `decisions`) is too short for one a row
  (the count `data-upper`). Rings lie inside a control's box.
- The play switches (`_play-switches.scss`) stand in their slot on the band row, bottom-aligned with the band, their
  height `--switch-h` (which the left hand's reach is measured against): each a native button with the switch role and
  `aria-checked`, at least 40x40, its knob over its label on a phone and a narrow desktop, before it on a desktop; on
  and off differ by the knob's side, the track's fill and a mark on the track's free side (a bar on, a ring off),
  never by colour alone. They follow the decision controls in the board's order, so Shift+Tab from the hand reaches
  them; an upright board has no slot and hides them.
- Own tiles: a held-back tile (kuikae, riichi) is recessed, never darkened: lower, smaller, flat, a dashed inner rim,
  its face and glyph colours kept; while some are held back the playable ones stand raised; a declaring or played
  tile is lifted and outlined in the accent, never into the 4px kept under the band.
- The zone device is decoration under every layer: lines and field tints from the centre's corners, drawn with
  `hypot`/`atan2` and clip paths from the same lengths. On a landscape board page it and the surface's gradient run on
  under the safe-area insets to the screen's edges the board meets (`--ox`, `--oy`, `--or`, `--ob`), never toward an
  aside beside or under the board (a storybook's lies below, past a margin of the bottom inset), the upper lines to
  the screen's top corners.

## The replay's controls

The replay's controls are on its board (`GameBoard`'s `replay`, the board marked `game-board--replay`;
`_replay-state.scss`, the replay chunk's, over the board's lengths from `game-board/_queries.scss`): one place per
control per viewport, never moved by what a stop shows.

- The moves stand in the play switches' place, bottom-aligned with the band: a round back, a step back, autoplay (the
  accent, the player's own action), a step on, a round on, and on a board with the desktop's chrome either end too (a
  smaller board's place holds five; the round list's first row is then the first deal and its foot, Last step, in
  view however far its rounds scroll, the replay's last stop, beside Home/End). On a phone and a short desktop the
  place ends before the bottom river's capacity reach.
- The options stand in the decisions' place, right-aligned at its end (a phone's band row past the bottom and right
  rivers' capacity reach, before the right hand where it crosses the band): speed, the viewpoint, hiding the hands,
  the round list's toggle. Where that row is too short for all four (`--opts-fit`, a length switch, never a measure)
  they stand as two rows of two, the round list's toggle in the band, the upper pair ending before the right strip as
  drawn (`side-strip-depth`, from the lengths `sideStripStyle` hands it). Upright, the options take a row above the
  moves, short of the right strip.
- The position (round, honba, step), a replay that is not the whole game (and where it ends at its last stop; a phone
  shows the label alone until then, its detail still read out) and the narration take the notices' place, under any
  notice. The narration is read out by its own polite live region, empty while autoplay runs; the narration drawn is
  `aria-hidden`, so it is in the accessibility tree once. Upright, the place spans the board above the options' row.
- A panel over the replay's board never covers its controls. On a board with the desktop's chrome it stops at the
  foreground's top, every option in the band row (the board beneath is inert), and on a wide desktop also leaves the
  left field to the status, starting past the left river's reach. On a smaller board (the panel-only exception) it
  takes all but the moves' row: the options hide but the round list's toggle, which keeps the touch way to every round
  and the end, and the status turns compact between them (the position and, at an incomplete recording's end, its
  label and an "Ends here" mark), the narration and the incompleteness's detail then read out only, since the panel
  shows the same stop; upright, the compact status and the toggle take the options' row. The panel's tiles keep their
  size; a result taller than its panel scrolls under its foot. The options come back as the panel closes, and a render
  that hides the focused control gives the focus back to the root. The round list opens above the options,
  right-aligned, over the board and a result's dimming, as tall as its rounds.
