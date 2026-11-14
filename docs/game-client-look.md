# Game client look

The visual specification of the v2 game client's board: what a player sees, how it is composed, and
how a change to it is judged. It describes the target in our own terms. The v2 client's layout rules
and its visual gate predate it and are reconciled with it; where they disagree, this document wins.
`docs/game-rules.md` stays the authority on what situations exist; this document only says how each
is shown.

Status: approved for implementation; the design acceptance and its drawn reference are recorded in
the plan. This document states the rules and the derived values; exact lengths within them are the
implementation's, and none overrides a safety floor, the contrast floor or an interaction rule
stated here. Remaining candidates are marked where they apply.

Three kinds of statement appear here, and a reader should know which is which:

- **Table conventions**: how riichi players read tiles on a table, verified against the World
  Riichi Championship and European Mahjong Association rules. These are not ours to change.
- **Composition decisions**: the board's structure and presentation choices, made deliberately
  after comparing the established online clients, which do not agree with each other on most of
  them. They bind the implementation.
- **Candidates**: exact attachments, forms and counts still open, marked as such. Where this
  document names a place or a form for an element, the invariant is that the element has one
  stable, predictable place within a viewport.

The derived proportions are the three reference viewports' values under the sizing rule
(Proportions).

## Principles

- **A map before tiles.** The board is a table with four seat zones a player perceives, not tiles
  on a void. Every tile has an obvious owner and every seat a fixed place for its identity.
- **A tilted table.** The core (centre and rivers), the opponents' strips and, on a desktop, the
  counters' place lie on one plane seen through one camera, two board widths away, its foot on the own
  row's top, in true perspective: each piece tapers and its tiles grow toward the viewer, but the
  counters stand upright and untapered, from their far edge at its shown scale. The table
  is laid out for that camera, deeper than the board, so that tilted it fills the flat table's
  height from its top edge to the own row, the own row itself the flat board's. The camera takes
  the steepest tilt of 20, 18, 15, 12 and 10 degrees on a desktop and 15, 12 and 10 on a phone
  (less than 10 reads flat and only softens the faces, so the board then stays flat) whose plane
  settles, shows the river tile across the core's middle within 5% of the flat board's and the
  nearest at most 0.85 of the own tile, keeps the side strips clear of the own row and a phone's
  core clear of its decisions' band, and shows the farthest faces at the face floor. Its felt
  bands (the top hand's foot to the top river, the core to the own row) open at most 0.95 river
  tiles wider than the flat board's; felt beyond that lies over the table's top instead, at most
  0.15 river tiles of it, the least margin that holds, and never narrower than the flat board's
  (the top band to a pixel, on a desktop to a tenth of a river tile, the bottom one to its least of 4px). A phone lays its tiles larger so its
  faces still show at the floor after the tilt (its plane's undrawn own row narrower where that
  keeps its river tile, its strips beside or above the own row as the flat board's, its centre
  lifted clear of the band), and its counters stay flat in their corner; one whose river tile is
  already at the face floor (an iPhone 11 with Safari's bars) stays flat, and so does one whose flat
  board drops its river tile near the floor for a larger own tile (about 786-793 wide by 296-334
  tall, beside neighbours that tilt 12 or 15 degrees); about 850-900x340 tilts 12 degrees where its
  neighbours tilt 15, its 15-degree plane's river tile falling under the flat one's. A phone's plane
  widens the felt under the top strip's meld room, not the room, so its deepest meld (an added
  kan) shows no nearer the top river than on the flat board. On a desktop the top strip's line
  starts further in where the left side strip, kept inside its flat place, comes in under its end
  (its melds lie there; its hand, at the other end, never moves): each side strip's farthest tile
  keeps 16px (or the flat gap) off the strip's end tiles, and the counters keep 8px (or the flat
  gap) off its first tile, never past the flat counters' left edge. A desktop whose width
  binds its river tile keeps the flat table's place, centred in its box, and tilts within it. The
  felt, its seams (drawn to the tilted centre's corners), the plates and calls (at the tilted points
  the table anchors them to, at their flat size, a plate standing on its edge toward the core, a
  top row plate raised further where its riichi stick would come within 10px of the core, 6 on a
  phone) and
  everything in front stay flat. Depth comes from the surface, the tile's edge and its shadow. One
  static transform per piece, no per-frame work. Decision: one light for every
  seat: every tile is one generated body (`entities/tile/lib/tile-body.ts`, `npm run bodies`), drawn
  for its pose on the screen, never by the stylesheet, so the light stays at the screen's top-left and the edge
  toward the screen's bottom whatever the seat: a body turned with its seat's frame is turned back, and a tile picks
  the body of its screen orientation (upright or across), its face art turned inside the face box. A lying tile's face
  is the brightest surface on the board, its corners rounded by 0.07 of its width, shaded with no outline:
  a lit rim on its left, a shaded roll on its right and a short roll at its foot, so tiles that touch read
  tile by tile without a line between them. Below the face its edge shows toward the screen's bottom: a flat ivory
  side, then the ochre base, the back's own layer, never near-black; the edge reaches 0.2 of a tile's width, which
  the geometry reserves (`TILE_EDGE_SHARE`). A face-down tile (a closed kan's end, an unrevealed indicator) shows the
  ochre back on top and its side ochre above, ivory below. Faces are not foreshortened by the body: the tilted
  camera does that; only the own melds' bodies, on the flat own row, are foreshortened (below). A tile nearer the screen's bottom paints over the edge of the one behind it, so no edge ever
  lies on a face: a river's later rows cover its earlier ones, the top river paints its rows from the centre out,
  the right river and the right strip paint each line from its far end down the screen, and an added kan's called
  tile covers the added one (the top seat's added tile lies nearer the screen's bottom and covers the called one).
  Tiles lying together (a river, a meld, a hand that takes no input, the dora) throw one soft cast shadow toward the
  screen's lower right, in the tile's width (0.12 right, 0.2 down, a 0.24 blur, 65% black), under all their bodies;
  a tile alone throws its own, and a hand that takes input draws each tile's shadow on its own, pulled in
  conservatively so it never reaches past the tile's left side.
  A chankan source's ring lies flat over the tiles.
  The own hand's tiles stand facing their player, each drawn as one generated body 1.5 of its width tall
  (`entities/tile/lib/tile-body.ts`, `npm run bodies`), not by the stylesheet: the back's ochre layer seen over its
  top, a pale top surface rolling over a crest into a calmer, darker front, rims that soften over the shoulder and a
  rolled foot, its corners rounded by 0.08 of its width. It is seen from low: the ochre and
  the top take 0.31 of its width, leaving a front 1.19 of its width tall, so the face never reads as square. The face art sits in a box on the front, 0.8 of the width,
  foreshortened to 0.93 and shaded with the front (0.8 brightness, so a red five's red keeps 4.5:1 on it), its corner
  label inside that box. Its tile box stays 4:3, the layout and tap target, the body
  drawn from its top and running past its bottom by the rest of its height, which the own row reserves in whole
  pixels, so on a phone the foot may be clipped by up to 1px at the board's bottom edge. It throws only the cast shadow, the hand's
  shared one, or each tile's own where the hand takes input; a held-back tile greys the whole body.
  The own melds lie on the table beside it: their own bodies, each face foreshortened to 0.92 of its
  height (the art and a sideways, stacked or face-down tile alike, a kan's stack 2 x 0.92 of a tile's width deep)
  over a deeper edge, 0.25 of its width. A flying tile takes its destination's body at take-off, turned with the
  flight, and throws one cast shadow. The own row reserves
  the deeper of the hand's overhang and the melds' edge.
- **Composed for ordinary play.** The design anchor is a mid-round state with real decisions on
  screen. Dense states (long rivers, four melds a seat, five dora indicators, long names) must
  stay legible and unambiguous but never reshape the ordinary composition. Exception: a river of
  21 or more discards, which real play almost never lays, may run under other elements.
- **One composition on every screen.** Far seat at the top, side seats at the sides, identities in
  the same places, decisions by the hand, at the 667x375 floor, on a notch phone in landscape and
  on a desktop. No opponent's hand or meld ever stands over the player's own hand: a desktop's table is a
  walled table without its wall, the own row standing between the side strips, the table as wide as that row and
  the two side lanes and centred; extra width goes to the side bars beside it, which hold the board's controls,
  never to felt inside the table.
- **The player's next task is the most prominent thing on screen.** At rest the hand dominates
  and the centre is one instrument; during an offer the offer leads; over a result the result
  leads. Table information stays scannable underneath. Colour marks an actionable or meaningful
  state, and tile identity (a red five), and nothing else.
- **Three tiers, by what a player loses when a thing is covered.** Every element on the board belongs to one tier,
  named before its place is chosen; the tier decides what may stand over it:
  - *Furniture*: the table itself. The felt, the zones' tint and seams, the plates. It lies under every tile and
    control; anything may cover it, and nothing moves, shrinks or keeps room clear to keep it in view.
  - *Table*: what a player reads to play. The tiles, the centre, the dora card. Furniture never covers it; one
    table piece over another is a layout fault, but for the overlaps this spec accepts (a river past its reserve).
  - *Task*: what a player must act on or must not miss. The decisions (a call, ron, tsumo, riichi) and their timer,
    the notices, a result or the game end's panel. It stands whole over the tiers below, which never cover it.

  The test for a new element: if a tile lay over it, could the player make a wrong move or miss what happened? No
  makes it furniture.
- **Show what is known, never what is guessed.** The board draws the state the server supplied:
  no invented draw, no decremented wall, no deposited stick, no revealed indicator before the
  event that reveals it. A local countdown is an estimate; the server's move is the fact.
- **Table conventions are followed, not reinvented.** Rivers, melds, the sideways tiles, the
  separated drawn tile and the riichi stick look the way riichi players already read them.
- **The live game is landscape only.** Its play area is the safe area of the landscape viewport,
  kept at least 10px off each screen edge on every board that is not a phone's so no tile meets a
  border, at whatever aspect ratio it has; nothing is letterboxed. Whether the board is a phone's is
  decided once, from the box the page would give it with that 10px gutter (the safe area kept), so
  the gutter never changes it. A portrait viewport under 768px wide sees the rotate panel instead
  of the board, regardless of touch or mouse input: there is no upright layout. A wider portrait viewport, a tablet's
  or a tall desktop window's, keeps the landscape board. The panel asks the player to rotate the
  device or widen the window and says that play and its timers go on. A replay's board is landscape only too: its
  panel asks the same and offers the game history, while its loading and failed screens, which hold no board, still
  show. A phone browser's address bar and toolbar take a third of the display in landscape: the
  live page stands as tall as the viewport they leave when collapsed, so a swipe collapses them and
  the board grows into the room, and a notice asks for that swipe while they show (Notices).
- **A phone's board ignores the bottom safe inset in landscape** (the user's decision). It honours the
  side and top insets only, so the hand sits on the screen's edge like Tenhou's and the home indicator
  overlays the hand's bared bottom edge.

## Composition (decisions)

```
+----------+-----------------------------------------------+----------+
| dora     |   [top melds] [ top hand ]                    |   cog    |
| round    | l   [T plate]  [ top river ]  [R plate]       |          |
|          | e                                           r |          |
|          | f        [L river] [centre] [R river]       i |          |
|          | t   [L plate]  [bottom river] [own plate]   g | replay   |
|          |   [toasts]    [kan][pon][chi][pass][timer]  h | moves    |
| furiten  |                                             t | and      |
| switches |                                               | options  |
|          |[ OWN HAND ...................... ][melds]     |          |
+----------+-----------------------------------------------+----------+
  left bar   table: own row between the side lanes         right bar
```

The diagram is illustrative: it shows the rings, the corners and the bars, not exact placements.

The table is centred on the board and is laid out as a walled table, its wall not drawn: the side strips stand at
its edges, running down beside the own row, the top strip along its top between them, and the own row along the
table's bottom between the side strips' lanes (an added kan's stack deep), so no opponent's tile stands above the
player's hand. The table is as wide as that row (a full hand of 14.6 own tiles) and both lanes. What it leaves on
either side is a side bar of the same felt, equal on both sides, holding the board's controls and no
tile. Two scales size it: the river tile (every river, the centre, the opponents' hands and melds) from the
height, the own tile from the width a full hand between the lanes keeps, at most 1.45 river tiles, so the own hand
is the table's largest thing; the bars hold the switches named and the counters' row only while the own tile keeps
1.3 river tiles; where the width cannot give it 1.2 river tiles, the river tile steps down instead. On every
primary desktop the river tile is bound by the height and the own tile by its cap, so a wider screen widens the
bars; only a near-square or narrow window binds the river tile by the width, where the own tile falls toward 1.2
and the felt beside the side rivers to their fourth rows' reserve. No band of the stack and no width of the table is
the decisions': they stand in a band along the own row's top, over the bottom river (Decisions).

A window taller than its table needs (the width binds the river tile: 5:4 and 4:3 screens, a near-square or portrait
desktop window, a portrait tablet) never spreads the table over the spare height, keeping the board at its
own aspect. The table is only as tall as its stack needs (or its side strips' lines under the counters), with no more
slack around the core than a height-bound board keeps (0.3 river tiles of air under the top hand), and stands
centred in the window,
the spare height above and below it. Everything is placed in the table: the top hand along its top, the side
strips' lines centred on the core (or under the counters), the plates, the decisions' band, the own row along its
bottom, and the bars' contents too: the counters, a replay's status and the cog at the table's top, the switches and
the replay column ending level
with the own row. The seams run to
the table's corners; the felt continues above and below it, the top field's tint above, the plain foreground below.

A phone in landscape keeps the composition with its own profile: the own row stays centred on the whole board,
wider than the column and passing under both side lanes, so the side strips end above it (a phone browser's
box too short there for three kans or for the decisions' band to hold the prompt stands its lanes beside the row
instead); the
decisions and the timer stand in a band along the own row's top between the side lanes, as on a desktop (Decisions);
the cog stands in the right bar, the replay's moves there too, at its
foot, in two columns where the bar's height above the own row does not hold one; the dora stand at the left bar's
top (a phone's top-left corner is too short for them under the plate), the play switches as a two-by-two block at
its foot, ending at the own row's top, the furiten mark above them and the notices between; the plates stand in
the core's corners as on a desktop (Badges). Over a panel the notices move to the right bar.

Four seat zones, top, left, right and bottom, are made perceptible on the surface. Decision: four
faint seams pressed into the felt (a soft groove over a fainter lip) from the centre panel's corners, the upper two to the play area's top corners (the table's, on a window taller than its table), the lower
two to its sides at the top of the foreground, so the whole foreground is the viewer's own; the
side fields carry a faint tint. They establish perceived ownership; they are not clipping
boundaries, and a long river may cross one. A seat's tiles and the score data facing it are oriented
toward that seat as on a real table: the top seat's tiles upside down, a side seat's on their side,
every river reading left to right from its own seat. Names, notices, callouts and controls stay
upright. The walls are not drawn; the wall count in the centre and the indicator slots stand for
them. The cost is the spatial picture: how much wall is left and where the dead wall sits are read
as a number, not seen, so emphasis on the count as the wall runs out is a candidate.

- **Core**: the centre and the four rivers in their pinwheel, compact and centred in the table, sized by the
  board's height. Its corners hold the plates as one rectangle (Badges); off a phone its bottom-left corner, under
  the left river's longest reach, also holds the notices as toasts, over the plate there, and the decisions stand in
  a band along the own row's top from the bottom river's start, over the bottom river and the own plate.
- **Perimeter**: each opponent's strip at the table's edge on its side, the top one along the table's top between
  the side lanes, every side strip clear of the own row's span. The felt between a side hand and its river is
  about four river tiles on a landscape window (the own tile's 1.45 cap keeps the table that narrow) and about two
  on a width-bound one: a hand reads as its river's owner.
- **Foreground**: the own hand and its melds between the side lanes at the board's bottom, with nothing reserved
  over it: the bottom river's longest reach stands right over the own melds' rise.
- **Side bars**: the left one holds a replay's status under the dora, which stand at the table's top-left
  corner (Dora indicators), and the furiten mark over the play switches, which end a band's height over the own tiles' foot; the right one
  the page's cog at its top and a replay's controls at its foot, by the own row. Nothing in a bar is a tile, and a
  desktop's panel, which stands in the table, leaves both usable. On a very wide window the cog and a replay's
  controls stand near the table's edge, not centred in the whole bar.

## Elements

- **Surface.** Fills the viewport, under the safe-area insets too, while the content keeps to the
  play area. Decision: a petrol felt in the dark teal family, lit broadly over the core and falling
  off slowly toward the edges, with a fine static grain as its only texture (felt at full size, gone in a
  thumbnail: no weave, motif or wear) and the zone device; nothing else is drawn on it. Off-white faces
  separate from it by value, the ochre backs by hue. The grain is one small repeating image under
  the gradient: no runtime noise, filter or blend mode, so a low-end phone paints it once.
- **Centre.** Decision: one panel, never square: off a phone six river tiles wide by four and a half tall, the side
  rivers (six tiles with a sideways one) running past its corners into the core's corners;
  on a phone six river tiles and at least 100px wide and the height left, at least 68px. Each seat's wind and
  score on the side facing it, turned to that seat and close to its edge, and in the middle the
  round name large (East 1, South 4, a West round when the game runs on) over one line of the wall
  count, the honba and the riichi sticks on the table (two lines where a phone's centre leaves under the
  48px its counts need between the side rows). Each side reads wind then score, all four at
  the same emphasis, tabular digits: the wind a quiet letter, the dealer's (East) on a muted red chip,
  as Mahjong Soul and Riichi City mark it in red; the score in hundreds with its last two digits
  smaller and quieter (`250` `00`), as Tenhou draws it. Every layout keeps the panel's width at least
  as long as a normal six-tile discard row, fitting the centre and tiles together.
  The rivers keep its corners. Score rows stand centred on their edge, clear of the side rows' depth at both
  ends; a row too long for that starts off its seat's left corner and runs toward its right, so it never meets the next
  side's; a short phone centre's side rows start nearer their corner, so a long score stays on the panel. The counts keep one line, a narrow centre's at a smaller size, down to a 10px floor
  whose tighter gaps still hold the line in a phone's centre. While a badge's differences show, the round and counts stay and no label
  names whose they are: that seat keeps its score, underlined, and the others' show as signed differences. One primary cue on the centre for the seat in turn: Tenhou's green bar along that seat's whole
  edge of the panel, its corners included, a shape the riichi stick never takes. Convention: a seat's
  accepted riichi stick lies on its side of the centre, as on a real table; this is where an
  established riichi is read, and the seat's badge only repeats it quietly, by a small stick under its band. Decision: the stick, a
  short pill with its dot, lies inside the panel between that side's score and the middle, so the
  gap between the centre and the rivers stays free and the turn bar on the edge and the stick read
  apart. The stick appears only once the declaration discard has passed without a ron, never when a
  ron or an abortive draw ends the hand on that discard; during the call window riichi is readable
  from the sideways tile and the callout alone. A seat's riichi marks reset at the next deal; sticks
  nobody collected stay in the pool.
- **Rivers.** Convention: each seat's river runs along its side, six tiles the normal row, three
  rows, reading left to right from the seat; a third row longer than six runs on along its own line;
  the riichi declaration discard lies sideways, and if that tile is claimed for a meld the
  declarer's next surviving discard lies sideways instead. Decision: the river starts at the
  centre's corner on the seat's left (the pinwheel). Decision: a claimed tile leaves the river, as
  on a real table, which costs the river as a single-place chronology: a claimed tile stays
  identifiable in the meld that took it, with its feeder, so what that seat has passed can still be
  read, but a player reconstructs the seat's full discard order from river and melds together; the engine, not the player, judges furiten. A narrow
  but visible gap separates a river from the centre and from its neighbours (off a phone 0.15 of a river tile,
  the top river's past the tile edge its rows drop toward the centre); tiles touch inside a
  river, rivers never touch each other. Decision, departing from the run-on convention for side
  rivers only: past eighteen discards a side river wraps its overflow into a fourth row toward its
  seat's edge, since a third row running on along a phone's short side would cross the hand; a top
  or bottom river keeps the convention, its third row running on along its line. In real play a river
  ends by twenty discards (a seat passes eighteen only through its own calls; of the
  stored rounds about a fifth reach eighteen, 8% nineteen, 1% twenty, none more), so layouts are
  designed and checked for twenty: two rows of six and a third run on to eight (a side river's
  fourth row of two), counting a sideways riichi tile, and the latest-discard gap: 7px across the light, and along it (a side
  river's from the tile before, a top or bottom river's from the row before) deeper by the 0.2
  tile edge that falls into it, so every seat's reads as one gap; a phone keeps 7px along it too,
  its edge two pixels and the reserve a pixel of its river tile at the floor.
  A river of 21 or more discards still
  renders in full but may run under other elements (the decisions, plates, a strip) or clip at the
  board edge; nothing shrinks tiles or moves controls for it, and it is not tested: no story or
  check builds one. Every row reads left to right from its seat, so the river reads in order and as its
  owner's in every orientation. Decision: a drawn-and-discarded tile is not told apart from one
  played from the hand (Tenhou shades it, Mahjong Soul does not); the rivers keep as few tile states
  as possible so the latest discard and the riichi tile are found at a glance.
- **Latest discard.** Decision: the newest discard is marked while it is the table's last action,
  whether or not the viewer has an offer on it, so a player can see what just happened: a small gap
  (7px; 10px along the right river's row) before it along its row and toward its seat, as a tile
  just thrown lies, with no ring, pointer or colour. The next draw ends it, the tile then lying in the river as any other; a call
  that claims it ends it too, the claim then read from the meld, and a result on it (a ron, an
  abortive or exhaustive draw) keeps it. During a discard offer this mark is the action source. A
  chankan offer's source is a kan in a meld and is marked separately, the whole kan ringed in its
  meld.
- **Melds**, every seat's. Convention: to the right of the hand from the seat's own view, the first
  meld farthest right and each later one toward the hand; the called tile sideways, at the meld's
  left when it came from the seat on the left, in the middle from the seat across, at the right from
  the seat on the right (decision: a four-tile open kan from across turns its second tile from the
  left, everywhere); a closed kan with its two end tiles face down (the form the rulebooks prefer;
  some tables turn the middle two); an added kan with the added tile sideways and stacked on the
  called sideways tile, on its centre-facing side, the two forming one column with both faces
  visible. A player reads who fed a meld from its shape alone, and tells a closed, open and added
  kan apart. Invariant: a visible gap separates the concealed hand from its melds and each meld from
  the next, at every seat and scale, so a closed kan never merges into the backs beside it; the
  implementation sets the gaps. A kan just declared, while a chankan may still rob it, reads as
  declared, not completed: no replacement draw and no new indicator show until the server sends
  them; a robbed kan stays readable as a robbed attempt in the result.
- **Opponent strips.** At the table's edge on its side, the top one along the table's top, at the
  river tile's scale: tile backs in live
  play, the faces the mode reveals in a replay or a revealed result, in the same place either way;
  the drawn tile set apart by a short gap only where the supplied state identifies one (a replay, a
  revealed hand, a live draw the server announced); a reconnect's snapshot cannot tell a held draw
  from the discard a call leaves owed (both leave 3n+2 tiles), so after one no gap is drawn until the
  seat's next draw; the seat's melds at river scale at the strip's far end (the
  hand's right, from the seat's view), as the own row's, so a call moves neither the hand nor the melds already laid. The strip is not a turn cue. Invariant: a strip stands apart from its own
  river, backs or faces, so that neither reads as a row of the other. Decision: a concealed hand,
  backs or faces, is 3:4 at the river tile's size (Tenhou's and Mahjong Soul's ratio), so an
  opponent's hand reads as plainly as its river. Decision: a concealed tile stands on its edge,
  seen from above, so a live hand never reads as face-down tiles (a closed kan's ends, the
  unrevealed indicators); the slot is kept whole, so a reveal shows the faces in the same place. The top seat's tile
  fills its 3:4 slot and reaches 0.44 of its width under it, its edge and a rise that keeps it tall
  without taking height from the stack, the felt under the hand giving it. The hand stands upright:
  the camera places its foot, but its tiles are not laid on the plane, so each is a rectangle as wide as the camera
  shows its foot and none leans with the perspective. Decision: a back shows at most 1.52 of its width tall,
  whatever the camera's tilt, so a steep phone or narrow-window camera does not stretch it. A revealed
  hand's faces lie on the table, so they keep the camera's foreshortening and start at its owner's edge.
  Its look: a thin off-white cap at its owner's side, 0.37 of its width deep, lit at its left end
  and shaded at its right; under it the back in the face-down tiles' bright ochre, lit under the cap and shading toward its
  foot as a lying back does, with its own small rounded shoulders. A side seat's tile shows its top only, no back face:
  0.72 of a tile's width across, at the owner's edge of its slot, the rest of the slot bare table; 58%
  off-white at the owner's side, 42% the back's bright ochre (the face-down tiles' colour) toward the centre, flat
  but for a short roll at its foot and thin rims, its end under it split the same way. Decision: a hand's tiles stand
  a one-pixel hairline apart, as the own hand's; a side strip's tiles run along the light, each covering the end of
  the tile above it, and a covered end is not drawn, so the hairline shows the table between them; only an exposed
  end shows (the run's lowest tile on the screen, and the tile above the drawn gap). While any tile of a hand slides,
  from the moment the discard leaves through the slide's end, every tile of that hand shows its end, a covered one
  under the next tile anyway, so a tile left above an empty slot never stands without its end. The drawn gap shows
  the end of the tile above it and is deeper by it, so the clear table past the end reads as the top strip's gap.
  Every seat
  keeps its melds in one continuous line to the hand's right from that player's view: downward for the left seat, upward for the right. The oldest meld stays at the far end;
  newer melds join toward the hand. Melds never wrap beside the hand or into parallel columns.
  All melds in a strip scale together to fit, beside the hand at its fullest with a drawn tile set apart, so a draw
  never resizes them, never below the 13x17 face floor where the line holds them there with their gaps closed; a
  rarer denser seat on a short phone box (four open kans at 891x331 or 844x251) takes smaller faces to stay on its
  line, never lying past it over the own row or off the board. A side strip's lane is its stacked
  depth at the table's edge, with no further buffer: no control stands beside a side strip; off a phone the own
  row starts and ends past both lanes, so no side tile, an added kan's stack included, stands over it. On a
  phone the side layout clears the own row using each meld's actual footprint.
  Each top meld stays above what it keeps clear of there, its tiles one size, scaling only where
  its line cannot hold them at the river tile. Decision: a side strip reserves the larger of a
  full concealed hand and a hand with up to four kans at the meld face floor. That reach has one fixed place per viewport, never read from the
  tiles held, and nothing else stands in it; a hand holding fewer tiles fills its reach from its start. Off a
  phone each side line is exactly that reach, centred on the core as far as the table's height allows (the own
  row stands between the lanes, so nothing below the core stops it): the left hand runs down from its top end, its
  melds toward the bottom, the right hand up from its bottom end, its melds toward the top; a seat's melds share
  the reach with the hand they leave, so they stand right after it. On a phone the lines run from the top margin to
  above the own row (or beside it, as far down as the box holds). The top strip's hand's full reach stands
  centred on the table; its line runs from the hand's right end leftward to the left lane's inner edge, never over
  the left lane. Its melds stay above the core, scaling where the line cannot hold them at the river tile, and
  an added kan's stack shrinks into the room above the top river.
- **Badges.** One shape for every seat, state and size: the name alone in a one-line band of one fixed width,
  a faint darkening of the felt with muted ink, so the names stay quiet table furniture and never draw the eye
  from the tiles. A plate is furniture (Three tiers): every tile, meld, river and control may stand over it, a
  replay's badge then pressable only where it shows. A name too long for the band is shortened in the middle (a phone or a best-effort desktop window may shorten
  ordinary names too) so its end, which tells AI players apart,
  stays. Its states each take a channel of their own and never change the band's outline or ink: away (an AI stands
  in for a human who left or never came, the human identity kept, cleared when they return) turns the name's ink
  red, its reason in the badge's tooltip and screen-reader label, red being reserved for it among the badge's
  states; riichi, a small riichi stick centred under the band, drawn over the felt so it moves nothing; the seat in
  turn, the green bar along the band's bottom edge (Turn cue). A seated AI player is unmarked on the board (its
  name, the seating and the game end tell it). The band is one height per tier, its box at least the control floor
  tall around it. Decision: on every board the four plates stand as one rectangle in the core's corners:
  top-left the top seat's, top-right the right seat's, bottom-left the left seat's, bottom-right the own
  one. The left pair's right edges stand a gap short of the top river's run-on and of the centre, the right pair's
  left edges a gap past the bottom river's run-on and the centre, mirrored about the centre's middle; the top row a
  gap above the centre and the right river's reserved top, the bottom row a gap under the centre and the left river's
  reserve (a riichi tile, the latest discard's gap and a tile's edge counted), mirrored about the centre's middle
  where the core's top and the own row allow, each row level otherwise. The band is as wide as the narrowest corner
  holds, at most eight of its ems. Places are fixed per viewport and viewpoint, never following how many tiles a
  seat holds. The corners place it clear of the tiles of an ordinary
  round, never of a river past its reserve, a meld line or a control that reaches it: those cover it, and no plate
  moves out of its corner for them. Decision: the badge carries no wind or score; the
  centre holds every seat's score, and hovering a badge shows the other seats' scores in the centre as differences
  from it (kept from the current board); hovering the centre does the same for the bottom seat's badge.
  In a live game the badge takes no press, no pointer cursor and no text selection; a replay's badge is a control
  that views the table from its seat, its tap area meeting the control floor whatever the drawn badge's size, and a
  focused one shows the accent's outline. The name shows on every board, shortened rather than dropped.
- **Dora indicators.** One card on the plates' colour: the five dora indicator slots (each
  indicator as a face once the event that reveals it has arrived, the rest unreadable backs; indicators are not the
  bonus tiles). Off a phone the card stands at the
  table's top-left corner, level with the top hand's top: over the left strip's lane, ending a plate's gap short of
  its inner edge where the top strip's line begins, so it reads as the table's and not the window's, both side
  strips' lines starting below it; in the bar beside the left strip only where its lines cannot start below it.
  Its dora are 0.8 river tiles, smaller where the room from the window's edge is short, never under 0.6, the five
  in one row at every size (three and two only where nothing else holds). Nothing is reserved under it: a
  replay's status stands in the left bar's field under it. On a phone the card stands at the left bar's top, the
  notices under it, its dora shrinking to fit a narrow bar, never under the 13px face floor. A replay shows no
  round or step beside the card: the centre shows the round, and the status reads both out to assistive
  technology only. The honba and riichi-stick counts are the centre's, under the round; the card does
  not repeat them.
- **Own hand.** Sorted, from its full reach's fixed start, the drawn tile set apart by a gap at the
  right: off a phone the left side lane's inner edge, on a phone the start of a full hand centred on the
  board; its bottom on the board's bottom. The melds stand at the row's right end, the right side lane's inner edge
  off a phone, as on a table, never larger than
  its tiles. Decision: the melds take 1 river tile (about 0.69 of the own tile at its cap, so
  they read as secondary to the hand), never past the hand's, where the row holds them
  beside the hand at its fullest (its drawn tile and gap counted), else shrink together to fit, never
  under the face floor. Invariant: for one viewport and one set of melds, no draw, discard, offer,
  riichi or callout changes a table tile's size, the hand's start or a laid meld's place; tiles still
  enter, leave, sort, rotate and take their drawn, latest-discard and selection offsets. Only a call
  or a kan refits the melds, inside their fixed room. Decision: its tiles are
  the play area's largest: on a phone for touch; off a phone (a desktop) what the width gives a full hand between
  the side lanes, 1.2 to 1.45 of the tile every other hand and river shares, 1.3 or
  more wherever the width allows, so the hand clearly leads the table; after a pon or chi
  there is no drawn tile and nothing is set apart. Every face stays readable in every state: after riichi the locked hand keeps its normal
  colours, and a draw with no offers is discarded automatically. An offered tsumo or closed kan
  stays available, with only the drawn tile discardable if the player declines it. Tile states are told apart at a
  glance: selectable, selected, held
  back by a rule (kuikae after a call, a red and an ordinary five alike; a riichi discard that
  breaks tenpai: quiet, never hidden), and the tile an answer already played. Decision: a held-back
  tile shows reduced emphasis, never darkness: greyed out (its glyphs grey, the face a step dimmer)
  at its normal size and position, with its edge and shadow kept and every glyph keeping its
  contrast against its face; selectable tiles keep their normal position too. A riichi-declaring
  tile is lifted, and so is the tile an answer played; neither is outlined, the accent ring on a
  tile being the keyboard focus alone.
- **Action source.** What an offer refers to is marked where it lies: the latest discard in its
  river, or for a chankan offer the whole kan in its meld (an added kan, or a closed kan robbed for
  kokushi musou). A discard's mark is the latest-discard mark, which the next draw ends; a kan's
  mark goes when its chankan offer resolves. No callout, animation or automatic notice covers the
  action source or the faces that identify it while an offer is open; a sheet the player opens does,
  by the player's choice.
- **Decisions.** The decision controls have one stable place by the own hand, ranked: a win (ron,
  tsumo) outranks every other action; kyuushu kyuuhai, offered at a seat's first turn, ranks with a
  win since it ends the hand, with playing on as the alternative; calls, kan and riichi come next;
  pass is subordinate and never the most prominent thing on screen; several equally valid actions
  are presented as equals. Decision: every control is the same flat box (one height, one least width, one type, no rim
  or edge), filled with its kind's colour: a win (ron, tsumo) and kyuushu alone take the bright accent, with dark ink;
  riichi takes the ivory of its stick, with dark ink; the rest are deep fills of one weight with a light label (pon blue, chi green, kan violet, pass a
  grey-green), so equal choices read as equals and nothing competes with a win. A soft sheen crosses a win's face (ron, tsumo) every few seconds and rests between, the
  controls' only motion, still under reduced motion or with animations off. The controls show exactly the offer the server made and vanish as soon as
  the player or a play switch answers it. Pass dismisses them silently; a declaration immediately
  shows its callout and plays its voice, while the table waits for the server to resolve the action.
  Decision: a call with a choice of tiles (which chi, which tile to kan) is
  one control per choice, all offered at once with no second step, and an illegal combination is
  never offered. A control shows tiles only where they are the hand's own and tell something the table does not: a
  chi its two hand tiles, low to high, the chis standing in that order as the hand lies (a red five's after the plain
  one's); a kan its tile only beside another kan; a pon and a lone kan none, the marked discard naming theirs.
  Riichi is a toggle that marks the discards that declare it on the hand
  and greys out the rest, wearing the accent as a ring inside its box while on; it can be untoggled until the discard is sent, not after. An expired
  decision stays visible and looks different from an open one; expiry is the client's
  estimate, and the server's resulting move (a timeout's discard or pass) is shown when it arrives.
  After a reconnect the open decision resumes with its remaining time, never a fresh one, and no
  stale selection survives. Decision: on a desktop the controls and the timer stand together as one cluster,
  fixed per viewport, in a band along the own row's top, right over the own hand: from
  the bottom river's start (the centre's left edge, clear of the notices' toasts) to short of the right strip's
  lane, under the centre and the right river's first tile and 6px over the own row's melds' rise. Every prompt, a
  call's, a riichi or tsumo turn's, kyuushu and a kan's choice, stands there, so the pass and the timer are found
  without looking. Its controls are 0.85 of a river tile tall, never under 40px, so a larger window never draws them
  smaller, along one row that grows left over the bottom river and the own plate, wrapping upward only where the
  band's width is used up (a narrow window, a long label). By design the cluster stands over the own river's tiles
  on its solid controls with a soft shadow, and on a short window a wrapped decision's top row rises over the right
  river's first tiles; neither the table nor the stack reserves room for either. Decision: covering the own river
  during a prompt hides nothing the prompt needs, since a call's source is never in the player's own river and the
  server never offers ron in furiten; the band keeps clear of every other seat's tiles, the own hand, the centre and
  the toasts. The controls wrap up
  from its bottom right: the timer at the right end, the lowest-ranked control (the pass) left of it, the offers
  left of the pass in rank order, the lowest nearest, wrapping upward, the highest on top. Every label in the
  cluster is the call buttons' size (0.38 of the control's height, never under 14px), the pass's too (Russian's
  «Пас»). Every source of a call lies in another seat's river or melds, so nothing a
  decision
  answers lies under it. On a phone the cluster stands in the same kind of band, right on top of the
  own hand: from short of the left strip's lane to short of the right one's, 4px under
  the centre and so the right river's first tiles and 4px over the own row, its 40px controls wrapping up from its
  bottom right in rows 2px apart (two rows hold `call_prompt`'s widest offers at 667x375, one at an iPhone 11's
  808x275 with Safari's bars shown), over the own river and the plates. Its bottom row passes under the left river's
  longest reach (its last tile's box, a riichi tile laid as the latest discard); where it cannot (a short centre over
  a long left river, 891x331), the band starts at the centre's left edge instead, as a desktop's does. It keeps clear
  of every other seat's tiles, the centre, the own hand, the left bar's block and the cog. A control keeps its
  tiles at every size.
  Every control keeps visible space around its label and its choice tiles, the
  longest label at the floor viewport included; a target that meets the size floor with its text
  touching its border has failed.
- **Input.** The contract the current board has, kept: a tile of the own hand is a button; one
  click, Enter or Space on a selectable tile sends it, a finger takes two taps (below), and a tile
  that is not selectable takes the press and does nothing. A decision control sends on one press,
  except the riichi toggle, which only changes what the next
  press means and is undone by pressing it again or by Escape. A play switch is
  a board control, not a decision control: pressing it changes what the client answers from then on
  and sends nothing itself. Focus stays in the hand through a turn, and an offer's controls are
  reached from it without the focus being moved for the player. An expired decision still takes one
  answer, since the server alone decides by the wait whether it counts; an answer the server refuses
  while the wait goes on reopens the decision as answerable, with the refusal as a notice. Decision:
  a finger discards in two taps, since a phone's tiles sit close enough for a wrong one to be
  tapped and a discard cannot be taken back. The first tap lifts the tile 15px;
  a second on it sends it, one on another selectable tile moves the lift there, and one anywhere
  else drops it. A riichi declaration's pick stays one tap, the riichi toggle being its first step.
- **Timer.** The countdown beside the decision controls (right of the pass, in the cluster) as large digits, the base time and the bank
  apart (`5 +20`), its digits and any caption each on a small dark chip in the plates' badge tone on every board, so
  they read over whatever the cluster covers (a plate, a river), the bank marked while it alone is draining, so a player always knows which time
  is being spent. Decision: a slot of fixed size and place, a caption line over the digits once time is up
  (the draining bank needs none), so expiry and the bank never move it or the controls. Answering dismisses the timer with
  the controls; there is no submitted caption or checkmark. It is the viewer's
  own: it shows for the viewer's open decision and round confirm only; the server sends no other
  seat's time, and none is drawn.
- **Turn cue.** One primary cue for the seat in turn, Tenhou's green bar along its side of the
  centre's edge, and one quiet reinforcement on its badge, a bar in the same green along the band's
  bottom edge on every seat, neither in the accent; no further turn decoration: the
  current board's "Your turn" and "Your call" labels and the line under the hand are decoration and
  go. Selectable tiles, the latest discard and the decision controls keep their own states, which
  are information, not decoration.
- **Furiten.** A small neutral status label (a dot and the word) in the left bar, over the play
  switches' column, the field ending above it,
  taking no room in the row so the hand never moves, not a button-shaped object and no prohibition sign, shown while the supplied
  state says the seat is furiten of any kind and cleared when it says so no longer; it gives no
  reason the state did not supply and never implies tsumo is unavailable.
- **Play switches.** Three toggles with one fixed place in the left bar, away from the decisions and outside
  the table, answering for the player while on:
  *Auto win* takes a tsumo offer at once and a ron offer at once (decision: no pause, since the callout and the result show the claim and its
  feeder); *No calls* passes a call prompt that offers chi, pon or open kan and no ron, before its
  controls show, and never touches the viewer's own turn (closed kan, added kan, riichi, tsumo and
  kyuushu stay offered); *Auto discard* discards the drawn tile after the fresh draw's one-second hold on a turn that offers
  nothing else, and leaves a turn with any other offer (tsumo, kan, riichi, kyuushu), and the turn
  after the viewer's own chi or pon, to the player. After riichi a fresh draw with no offers is
  discarded automatically even with *Auto discard* off; a kan or win offer waits for the player
  unless *Auto win* claims the win. Automatic riichi discards use the same unseen-wait guard as
  the switches, so a repeated wait, reconnect or refusal never causes an automatic resend. A
  win always outranks a discard or a pass, so with both switches on a tsumo offer wins. A switch
  answers a wait the first time the client sees its id while the switch is on, and never a wait it
  has already seen: not the decision already open when the switch is turned on, so nothing moves
  under the player's finger; not the same wait re-sent after a reconnect, which the server re-sends
  only while it still owes the seat an answer (one given before the drop never reached it), so the
  decision resumes answerable, for the player to answer again, never a switch; and not a decision
  the server's refusal reopened, which is the player's to answer again. Decision: all three reset
  at each deal, and when a reconnect's snapshot shows another hand or a round result pending,
  since a switch is an instruction about this hand.
  One setting in the settings menu, off by default and kept in this browser, excepts Auto win from
  that reset, so a player who turned it on keeps it into the next round (Tenhou's manual clears only
  its no-call every hand and its auto-discard when the mouse was touched; Mahjong Soul players ask
  for auto-win to persist); off, no win is taken on a later hand the player might have declined.
  Turning the setting on also turns *Auto win* on, and turning it off leaves *Auto win* as it is
  until the next deal.
  They survive a reconnect within the hand in the mounted client; a reload or a new tab starts with
  all three off, the setting staying as chosen. They are the client's standing answers, taken exactly where the player's
  press would be, with the decision's wait id, so the server, which keeps no preference, sees an
  ordinary answer; the latest-discard mark and the table are unchanged by an automatic pass, and an
  automatic discard travels like a pressed one. Decision: every switch is one press away, never
  behind a panel. They stand as one column at the left bar's foot, ending at the own tiles' foot on a desktop,
  whose own row starts past the left side lane, and on a phone as a two-by-two
  block at the own row's top, whose own row passes under the bar, so the notices keep a field above it. Their size is the tier's, never the decisions' larger one. Where the bar
  holds the whole names, each switch shows its name at the plates' text, narrowed with its label to the bar, never
  under 14px nor three quarters of the plates' text, so a larger board never names them smaller (16-28px over the
  desktops that name them: 1280x720, 1366x768, 1536x864, 1600x900, 1920x1080, 2560x1440); a bar that holds no label
  that large (1280x800, 1440x900, 1680x1050, 1920x1200, 1280x1024) shows the letters' form instead (the bars are
  held wide enough for a 12px label where the river tile allows, which keeps the notices' field its width);
  elsewhere (a phone, a narrow bar) the column is one joined bar with
  a square cell per switch showing its letter (A, C, D in English; each language picks its own) and
  a cell under them that shows each letter's name until pressed again, above them, off the own hand. The name is each chip's tooltip and its accessible name in every form.
  Each switch shows on and off apart, not by colour alone (Mahjong Soul colours its letter, Tenhou
  checks a box on a phone and dims the tab on a desktop): on, the turn cue's bar along its bottom
  edge, as on a badge and the centre; off, no bar. The text stays centred either way. Each chip meets the control
  floor; a switch is reached from the hand's focus like a decision control. Not on a replay board;
  the decisions stories show them, on and off.
  The own hand and core keep their sizes and places. A visible live board never hides the switches
  because of its aspect ratio.
  No auto-sort switch: the hand is always sorted. No forced auto-discard after idleness: the server's timeout and the AI
  stand-in cover an absent player.
- **Settings.** Not built: a settings sheet exists only while it has an entry, and it has none. The
  play switches are not settings: they last one hand and stay on the board.
- **Callouts.** Decision: a call, a riichi, a kan, a kyuushu kyuuhai declaration and a win show as
  one word on a borderless chip over the caller's own river, upright, three river rows' worth of type,
  a win's word in its own colour, covering no decision control and no face of the own hand; it may
  cover an action source for its moment (decision: size over a clear source). A local declaration
  appears on selection, without moving tiles or changing scores. A matching server confirmation
  does not repeat a lone callout or its voice, even after its popup expires. Another player's winning
  call replaces it when the server resolves priority. A double or triple ron
  shows every claimant's at once. It shows for 1.25 seconds: a 250ms fade-in shrinking from twice its
  resting size, a 500ms hold, then a 500ms fade-out. In live play it remains until
  then or until a newer call replaces it; in a replay on its own clock too, kept as the reader moves
  on through its round, gone on stepping back past it or into another round. Reduced motion keeps only the fade.
- **Tile motion.** Draws travel from the centre to the separated hand slot and discards from hand to river in
  120ms, with a faint trail (its copies drawn without a shadow; the tile itself throws one cast shadow, and a
  replay's tsumogiri keeps its shade). The latest discard settles into its river slot in 120ms when its mark ends.
  A travelling tile takes its destination's body at take-off (a discard leaves the hand as the lying
  river tile, a call into the own melds as the lying own meld tile, a draw flies as the standing body), and keeps it
  and its shadow throughout, its size changing continuously from source to destination; landing on the tilted table it flies already in its slot's look
  (the camera's taper and squash), so it lands with no pop. The body
  flies upright on the screen in its slot's orientation, so the light and the edge stay fixed to the screen. Rearranging hands, settling
  discards and moving or resizing laid melds animate their actual tile wrappers inside their group, retaining its
  shared edge and shadow and native button feedback. Meld resizing keeps its tiles moving and scaling together
  under that shared shadow; on the tilted table their offsets are the slots' own, taken back through the camera, not
  a uniform scale. A discard still changing size or orientation in flight finishes as a travelling tile.
  The hand closes gaps and sorts over 200ms after the discard's flight, with an additional 300ms pause in live play.
  Replay settles the previous stop's tile movements before measuring the next move, so rapid stepping animates
  only the latest move and never waits for an animation backlog. Calls assemble their
  meld from the original hand and river positions; travel time follows distance at the local tile scale, bounded
  to 80–300ms. Starting hands and indicator slots appear immediately at each deal. There is no drawn wall.
  Opponents' revealed hands replace their standing backs one tile every 30ms, without a flip; waiting backs stay
  in their native hand slots, retaining the hand's shared shadow and the side hands' gaps. The hand stays
  automatically sorted and keeps its existing hover and selection feedback. Motion never blocks input, delays
  game state or invents a hidden tile identity; later events preserve unaffected movements. A fresh page,
  reconnect, replay jump or viewpoint change shows the requested position immediately. Reduced motion, asked by the
  system or by the settings menu's Animations switch, disables
  tile travel and staged reveals. Match standings fade in over 1.5 seconds and fade away over 250ms when dismissed;
  round-result panels, their opening delay and their yaku presentation are unchanged.
- **Page corner.** A settings cog, small, at the right bar's top; where the bar is too narrow for its tap
  target and a gap (a narrow window), in the board's top-right corner instead.
  The icon is smaller than its control-floor tap target.
  It reserves no room in the strips, hands or badges, which keep their places; a
  panel may cover it. Decision: its menu holds the sound switch, a language row (one compact strip of the
  three languages by their native names, the current one marked), then the
  connection status (a dot and its whole label); a tap outside the menu only closes it, and Escape closes it back to
  the cog. While the status has a word to say (a drop, an end), the cog carries a dot in the status's tone, so a drop
  shows without opening the menu. A replay has the same corner and cog, its menu the sound switch and the language row alone. The live
  board has no way back of its own; the rotate panel in a narrow portrait viewport keeps
  one, which asks the leave question, and an end's panel offers the lobby.
- **Sound.** The live game plays an original synthesized resin tile clack and a soft two-note countdown tone,
  plus a soft 180 ms chime once for each newly seen decision offering chi, pon, kan, riichi, ron or tsumo that still needs
  the player's answer. A previously seen prompt repeated or reconnected, a refused answer reopening, an automatic answer and a
  turn offering only a discard or kyuushu do not chime. The decision chime is live-only. The supplied
  recorded voices play as their callouts first show, with an additional voice when the server confirms a yakuman result.
  The countdown beeps for each of the last five
  seconds of a decision that runs
  longer than five. A reconnect's snapshot plays nothing. A replay plays a move's sounds (no beep) on a step on to the
  next stop (Next, autoplay, a held Next, the wheel), never on a jump, a step back or a result's page. A browser
  plays no sound before a click, tap or key on the page, and a wheel is none, so with the sound on a replay always
  opens on its seating, a linked position included, and the wheel never leaves it: Start (or a key or a control) is
  that click, and goes on to the linked position. The switch is on by default and kept in the browser,
  shared by the live game and the replay.
- **Notices.** Reconnecting, a lost seat, a refused move, a message the client could not read, tile
  faces that did not load, a phone browser's bars taking room a swipe would give the table (the
  quietest, last among the ongoing ones): decision, off a phone they stand as toasts of up to two lines, their text the
  board's share and never under 14px, in the core's bottom-left corner: past the left strip's lane to short of the
  bottom river's first tile, under the left river's longest reach and over the own row's melds' rise, stacked down
  from its top, over the left plate. The left bar (105 to 150px wide on primary desktops)
  squeezed them to 12px and wrapped them, so that felt, which no tile or control reaches at any size, holds
  them; a toast wraps to
  a second line where its words need it, and a stack the felt cannot hold shows its first toasts, the last one shown
  saying how many more its sheet opens ("+N"; a short window holds one two-line toast and a one-line one); a
  lone toast taller than the corner runs past its foot over the table, a task over the tiers below. A toast's
  words that run past its two lines end in an ellipsis, the whole in its title and in the sheet, the cut toast
  opening it; a clamped toast is at least its 40px target tall; a way out (Reload) stands beside the toast's words,
  40px tall. Over a panel, which may stand over that corner, they stand in the
  left bar's field instead, wrapping and clamped to whole lines there. On a phone their one place is the left bar's top, at the bar's
  width, their text smaller where the bar is narrower than 7.5 of its ems (to 11px, which an 84px field holds), down
  to above the furiten mark, outside the table, which leaves free, so an automatic notice covers no tile, plate,
  control or panel; a word breaks only where it alone is wider than the line, never hyphenated; a notice whose words
  would run past three lines in a narrow field shows a brief form there (Tiles shown as text; Reconnecting…), its
  whole words in its title, in the sheet and in what is read out; and a way out (Reload) is a 40px button on a line
  of its own under the words, its label on one line;
  worded for a player, and a recoverable interruption looks different from an end. Several stack there,
  ongoing conditions first; it stands above a panel's dimming. A notice never loses its ending silently: one taller than its place shows whole lines and a
  "Show all" control, which opens the whole message in a sheet. Decision (step 4.2): "Show all" is the
  clamped notice's last line, its own box 40px tall rising over the words above it, and the whole notice its
  target; where even one
  line a notice leaves the stack too tall (a phone's reserve over a panel holds one notice), the last
  notices are left out and the last one shown says how many more it opens ("+1"); the sheet shows every
  notice of the stack whole, each with its way out (Reload), so the clamped notice's control moves there.
  The player chose it, so it covers the board as a panel does, the
  board inert beneath it, the focus in it and back on "Show all" when it closes, by Close or Escape
  (Escape closes it alone);
  it says that play goes on, with the seconds left while a decision or the round confirm is open, as
  the rotate panel does. It ranks under an end and the leave question and over the table's panel, which
  comes back as it closes; it stays open while any notice remains, and wherever it closes the focus
  stays on the board. Each notice is announced once, never its clamp; each showing of calls is
  announced once too, on the live board and in a replay, and a replay announces no calls while it
  jumps (a round, an end, the round list, an address), while a step is held (Next or Prev, pointer
  or key repeat) or on the wheel. An ongoing condition (reconnecting, a seat lost, faces that did
  not load, a message the client could not read) stays until it recovers, is rebuilt or ends; an
  acknowledgement (the seat back, a refused move) leaves on its own after a moment. Nothing
  dismisses a failure that goes on. A connection replaced by another tab is an end, with its reason,
  its corner status in the ended tone rather than an error's.
- **Panels.** Round results, the seating at the game's start and at its end, and the leave question use
  a legible overlay area over the board and dim it beneath; each has the size its content needs, not
  the core's, covering whatever of the board's middle it needs (the rivers, the centre, a call's
  announcement). A round result's panel is at least as wide as its yaku, value and indicators side by side need,
  where the board holds that, so a short phone box lays them out abreast. A board under 290px tall (an iPhone 11's
  896x275 and 808x275, the A25's 844x251, Safari's or Chrome's bars shown) widens the panel, lays the yaku in two
  columns at an 18px pitch and each player's change and total on one line, so a five-yaku hand and a double ron
  show whole there; where a notice beside it narrows the panel, the total goes back under the change. At the
  primary sizes every panel, a round result included, fits whole; a board too
  small to hold it (a best-effort narrow window at most) scrolls it inside its area, first a result's
  yaku, value, indicators and score rows in place, then the panel itself, its primary button and
  countdown kept in view. A panel may cover the page
  corner, which reserves no room; the leave question is modal: it says that an AI takes the seat over
  and makes staying the clear default. The seating shows the game's length and the round, every seat's
  wind and player, the dealer, AI players, the viewer and each seat's score. Live, it is the game's opening screen
  (Tenhou's): it stands over the dealt table (the closed hands, scores and round under it, the board left playable)
  from the game's start until play starts, with one primary OK and the seconds left under its label, as a round
  result's confirm counts its time; Enter or Space presses it. The OK is the seat's start confirm (Tenhou's
  NEXTREADY): pressed, it stays in place, disabled, reading "Waiting for others" while its time counts on to 0. Play
  starts, with the first draw, once every player confirmed or the server's start timeout ran out, and closes the
  screen, as does a round's or the game's end; a seat the server awaits no confirm of closes it with the OK, which
  then sends nothing. A reload during the start confirm opens on the same screen, its OK owed or waiting. A page that
  joins a game in play (a reload, a late join) opens on the same screen once, for five seconds, with the round,
  winds, dealer and scores as they stand now; its OK sends nothing;
  a reconnect on a page that already showed it brings none, and a page joining at a round's result opens on the
  result. It is a normal game screen and never speaks of sound, though its OK, as any first tap, is the gesture the
  browser needs before the game's sounds play. A replay opens on the seating with a Start in the OK's place (on a phone in landscape the seating also names the viewpoint), and off
  a phone's short board the replay's seating (start and end) covers the table's centre block, its text scaled to the
  block.
  Decision: off a phone the notices' place is reserved whether or not a notice shows, so a panel's box and its
  tile size never change as a notice comes or goes. On a desktop a panel stands centred on the core, inside the
  table column, so the bars (a replay's status and controls) stay usable beside it; on a
  phone it stands centred on the board both ways, and only while a notice shows does it narrow to leave the
  notices' column beside it. A desktop's panel fits its content whole.
- **Round result.** Decision (the established clients order it differently; Tenhou's viewer puts
  the total first): the winner and how (ron, and from whom; tsumo; a head bump names who lost the
  ron); the winning hand with the winning tile set apart and its melds in their shape; the yaku,
  with han where han are meaningful and yakuman names and multipliers where they are; the dora,
  red and ura counts apart, the ura indicators only for a riichi winner and per winner in a double
  ron, both kinds in a column of their own beside the value, under one small "Indicators" caption
  (a panel too narrow for columns, on one line after that caption), so they never read as the dora;
  the total (han and fu where meaningful, the limit name, the
  points) large; a note where a seat's payment is not the hand's value (pao, honba, collected
  sticks); every seat's change and
  new total together, cumulative through a double ron's pages or final, never mixed; then one
  primary button, with the countdown where the server set one (the game's last result has none),
  a pager only when there are more winners (early pages advance, the last confirms), and, once
  confirmed, that the seat waits for the others (after a reconnect too). A triple ron shows three
  claims and then an abortive result with no payouts. An exhaustive draw shows who was tenpai with
  their hands, noten seats unrevealed, and the payments, an all-tenpai or all-noten outcome said
  rather than left blank; a nagashi mangan names who made it, shows their river as the proof and
  the mangan payments, without a winning tile or a yaku breakdown, and still the tenpai verdicts;
  an abortive draw says why (four winds, four riichi, four kans, triple ron, kyuushu kyuuhai with
  its declarer). A first-turn win is an ordinary result over the board as it stands: empty rivers
  for tenhou, the earlier seats' first discards for chiihou. In live play a result whose round ends on the page
  opens 1.5 seconds after it, a draw's as a win's, so the move that ended it (the haitei discard, the fourth wind
  or riichi, a win's call) lands and is seen first; a page that joins or reconnects at a result opens it at once,
  and a replay's result, a stop of its own past that move, waits only after a win's call. A press on the dim beside
  a result hides the panel and the dim to show the board under it (the last discard, the rivers, the revealed
  hands) until the press ends; the countdown runs on meanwhile. The result itself takes it, wherever it shows.
- **Game end.** The seating panel again, its seats in the server's placement order with table points
  and adjusted results (uma and oka) told apart, signed values kept, the leftover riichi sticks (or a
  note that the game's rules award them to nobody), the viewer's seat marked, and the ways on (the
  last result, this game's replay, the history, the lobby). No per-round ledger. A game that ended by
  tobi or at a round threshold is shown as completed, saying how it ended as the server decided it
  (tobi, the game's length, the target score reached in the extension, the extension's last round),
  never as a failure. An ended session says
  why and offers the way back; it is not quiet.
- **Replay.** The board unchanged, its geometry identical to live play's, drawn from the chosen
  viewpoint seat, which need not be the reader's; plus controls with the
  moves, play, the hide-hands switch and the round list, readable at the
  floor viewport. Decision: no narration; the board itself shows each move and its centre the round; off a
  phone the left bar shows the round and the step's count (`153 / 210`) under the dora, the whole position read
  out to assistive technology; on a phone the position is read out only. Its calls are read out as the live board's are, silent while the reader scrubs (see
  Notices). Decision: off a phone the controls stand at the right bar's foot, by the own row, the moves over the
  options, each 0.95 of a river tile (56px at 1920x1080, never under 40px), in the fewest columns that keep them in
  the bar's lower half at that size (two on a primary desktop), else the fewest that hold them at their size; the
  status (an incomplete recording's note) in the left bar's field under the dora, up to 24 of its ems wide over the
  table past the field's width, on the notices' backing. On a
  phone the column stands at the right bar's foot, in two columns where the bar's height does not hold one. A
  replay has no decisions, so its column and live's pass and timer never meet; the own plate stands where
  live's does, and the switches' place stays empty. Decision: the moves are the viewpoint seat's turn
  back (its last draw or call), a step back, play (in the accent, the player's own action), a step on and
  its turn on (past its last turn the round's result, then the next deal), with
  a round back and on at either end off a phone (on a phone the round list reaches them by
  touch); either end of the replay is the keys' and the round list's (its
  first row and its foot, Last step, always in view). The options are hide hands and
  the round list, with the next seat's view before them off a phone. Every control shows
  its name and key at once on hover and keyboard focus. Decision: autoplay has one pace, no speed
  control. Decision: the viewpoint changes three ways: the view control (off a phone), pressing
  another seat's badge or its score in the centre, and pressing a seat's name on the seating, which
  marks the seat viewed from; so a replay's badge pins no differences (hovering still shows them).
  Decision: a replay greys a discard of the tile just drawn (tsumogiri) in every river, one shade over
  its face alone (its edge and shadow stay as any tile's), and marks it with a small dark corner in its face's bottom-left corner, placed by the tile's box;
  live play marks none. A panel over a replay's board never covers the controls, so the replay
  always moves on. Decision, a panel-only exception: on a phone a panel
  takes all but the moves, the options hide but the round list's toggle, and an incomplete
  recording's "Ends here" stands between them, compact (before the group where they share a row), and the panel's
  tiles keep their size, its content scrolling with its pager and action in reach. The options return
  as the panel closes. Loading, not found, incomplete
  and damaged replays each say so, as does a replay that cannot be drawn at a later stop (the failure
  screen); an incomplete one shows no result for its unfinished round.
- **Material and type.** Neutral off-white tile faces (not cream) with room around the glyph, rolled rims lit
  from the screen's top-left, a small consistent ivory-over-ochre edge and shadow; a red five reads as red at every scale, in a river, a meld, a revealed hand and a result;
  backs in one colour, the canonical yellow-orange: an ochre plastic, darker and less luminous than
  the accent so a strip of backs never reads as a control, its darker shade the back's layer under
  every tile's off-white body. Decision: the face artwork (the committed SVG set) stays, its ordinary red
  darkened from #b93c3c to #9a2424 (fill and stroke) so its thinnest strokes keep 4.5:1 on the face
  once the camera resamples them, the red fives' brighter #d71e1e unchanged and the clearer for it; the room
  around the glyph comes from the tile box, not from new drawings, and a glyph that is still
  unreadable at river scale with that room is reported, not redrawn in a ticket. Decision: the lobby's
  system sans-serif stack, with tabular digits wherever numbers align; no downloaded fonts or
  monospace. Decision: one accent colour, used only for the player's own action (the primary
  control, the riichi toggle, a focused tile); the latest discard and the action source
  are neutral, the turn cue Tenhou's green, and every text, mark and glyph on every face state keeps 4.5:1. Text
  keeps a readable size at every supported viewport; the gate's 10px floor is a safety limit, never
  the size to design to.

## Out of scope

Decided earlier and not reopened by this document: player avatars, titles and other identity
decoration beyond the badge; a tenpai mark (the hand's waits and their remaining counts, live or in a replay); and hints that
judge the hand for the player: what each discard would wait on, which discard reaches tenpai,
shanten counts, safe tiles. The board gives no help beyond the state the server supplied. The
client is localized (ja, en, ru) under `docs/i18n.md`; this document names its English text.

## Proportions

Relationships first. The sizes come from one sizing rule; the derived column records the ratios it
gives at the three reference viewports and is not a range for other screens: 1280x800, 1920x1080 and
other phone heights follow the rule and are checked by the gate, not by this table.

The sizing rule. The board's sizes, its family, its chrome tier and every footprint it reserves
come from one function of the board's box (`boardGeometry`); the styles place from them. A
landscape board is a phone when the box it would have with the 10px gutter is under 520 px high,
and then it takes no gutter; anything else is a desktop, one family, with the gutter; the chrome tiers
(small under 1100 px wide or 520 px high, large from 2000x1200) are read from the padded box.
Deliberately, a board 520 to 539 px tall without its
gutter can be a phone (always so when the safe area has no top or bottom inset, since the gutter
adds only what exceeds the safe inset), and a phone always has the small chrome. Off the small tier the
chrome's px scale continuously from the regular record to the large one with t = clamp(min((W − 1100)/900,
(H − 760)/440), 0, 1) of the padded box: a desktop under 760 px high stays at the regular record (t = 0), and t
saturates at 1 from 2000x1200; past it a large board's chrome (plates, switches, cog, counters, text) grows with its
river tile from the tile a 1200px-tall board takes (68px), so a 2560x1440 board's is 80/68 of the large record. The
step from the small
chrome to the regular one stays, and a phone scales its chrome from the small record on its own.

On a desktop two scales are solved: the river tile from the height, the own tile from the width. The river tile is
the largest whole-pixel size whose vertical stack fits the padded box's height, top to bottom: the top hand (a tile
and its edge), a gap of 0.1 river tiles, the core (the top and bottom rivers' three rows with their latest-discard
gaps around a centre 4.5 river tiles tall, 0.15-tile gaps, the top one past its rows' tile edge), the bottom river's
edge, the own melds' rise and the own row at 1.45 river tiles with the deeper of its edge and the melds' (reserved
at that size even where the width takes the own tile smaller, which barely changes the row's height: an added kan's
lying stack, 1.84 river tiles deep, rises over a hand smaller than 1.38 river tiles, and a larger own tile shrinks
that rise as much); whose side strips' reach fits
that height; and whose own tile the width gives at least 1.2 of it. The own tile is what a full hand of 14.6 own
tiles leaves between the two side lanes within the bars, at most 1.45 river tiles: bars that hold the play switches
named and the counters' one row where the own tile keeps 1.3 river tiles with them, else bars that give up the
names, then the row (which then stands over the left lane, the side strips' lines under it), else bars of 96px; the
table is that row and both lanes, centred, never narrower than the core and both lanes. The cap is the own hand's: at 1.45 it is the table's largest thing at a
glance, the felt between a side hand and its river about four river tiles on 16:9 and 16:10. The own melds shrink
into what the fullest hand leaves, above the face floor (four open kans to about 0.95 river tiles on 16:9, 0.86 to
0.89 on 16:10 and about 0.8 on a near-square or width-bound window). The table keeps
no margin inside the gutter, and the height the stack leaves goes above the core, under the top hand. A desktop's
decision control is 0.85 of a river tile tall, never under 40px, so it never shrinks as the window grows; its label is 0.38 of it, never under 14px, and the controls' least width (4/3 of it), gap (1/8) and the timer
(1.75 of it, at least 72px, holding `10 +20`) scale with it.
It gives river and own tiles of 39 and 56px at 1280x720, 35 and 50px at 1366x657, 42 and 60px at 1366x768, 43 and
56px at 1280x800, 49 and 66px at 1440x900, 47 and 68px at 1536x864, 58 and 77px at 1680x1050, 60 and 87px at
1920x1080 and 80 and 116px at 2560x1440, 33 and 41px at 960x1000, 40 and 49px at 1100x1000, 49 and 59px at
1280x1024, 59 and 71px at 1502x1551 and 26 and 32px at 800x600 (width-bound: the own tile toward 1.2 river tiles);
the river tile grows with the window's width and height, never falling back as either grows.

On a phone both tiles are solved together from the box, led by the own hand tile: first the largest own tile that
fits with a river tile at the 13px face floor or more, at most as wide as lets a full hand's row, centred on the board,
stand within the board's width less its margins, never under 36x48 (32x42, the tap floor, where 36x48 leaves no river
tile at the face floor, or none whose band holds the widest prompt), and at least 4/3 of the river tile; then the largest river tile whose own tile is within 2px
of that largest own tile (`PHONE_OWN_GIVEN_FOR_RIVER`), with the largest own tile that fits beside it. So a taller or
wider box never costs the own hand more than those 2px, which buy the rivers a step where they would otherwise give
up a whole tile size to a pixel of own tile (the A25's box keeps 17px rivers for a 41px own tile rather than 13px ones
for 43px). The decisions' band holding the widest prompt comes before all of that, over both own floors, so where a box first
holds it the own tile falls back, 7 to 14px (at 333 to 336px tall from 636 to 724px wide: 43 to 36px at 640, 48 to
36px at 720), and the river may step up 3px; a right bar holding a replay's column is preferred at each river tile. A box too short for the face floor at the tap floor (a phone browser's bars shown, under about 275px)
takes the largest river tile that fits over the 36x48 floor instead, else over the tap floor where that lifts it.
A phone's table column is 25 river tiles
wide too, centred, and each bar beside it only as wide as what the bars still hold needs with their gaps: the left
one the counters at the 13px face floor, the switches' two-by-two block and the notices at their 11px floor; the
right one the cog, a replay's moves column (two columns where the bar's height does not hold one) and the notices
over a panel (94px at the floor, which bounds the river tile on the narrowest phones); no bar reserves anything for
the decisions, which stand over the own row. As far as the bars keep that, the column widens so the top strip's line
holds four kans at the face floor beside its centred hand. Its side strips' lines run from the top margin to above
the own row, which passes under both lanes, so the own tile is also no larger than lets a full concealed hand fit
that line. Where that line would not hold three kans at the face floor (their gaps closed, reaching at most into
the own row's clearance) or the decisions' band not the prompt below, or would cost the river tile, and the bars
allow it, the column widens instead until both lanes stand beside the own row, so both lines, the switches and the
right bar run down to the board's foot (an iPhone 11's 808x275 and a Galaxy A25's 891x331 with their browsers' bars
shown); elsewhere the lanes stay
at the column's edges, beside the rivers. A
phone's side strips reserve the
full concealed hand and as much of a line of four kans at the face floor as the box holds, a denser
seat's melds closing their gaps down to 2px to stay on it, then shrinking under the face floor, all together, to
end on it; the right strip's line always holds three pons at the face floor beside the
hand they leave, whatever that costs the river tile. The
decisions' band, from the centre's bottom to the own row's top less its 4px clearances, always holds
`call_prompt`'s controls at the widest of the three languages' labels (the pass and the timer, two tiled chis, a pon
and a kan, 450px in one row) in as many 40px rows, 2px apart, as the band's width needs: one where it is that wide,
else two; a river or own tile whose band would not hold them is not taken, unless no tile in the box holds them (the
floor display's Safari box, 667x236, whose band is shorter than a row). The own tile is also the largest whose right
bar, from under the cog down to the own row's top (to the board's foot where the lanes stand beside the own row),
holds a replay's moves column; else the least at that river tile: this bound caps the own tile only, never the
river tile.
The gap below the top strip is 6px (an added kan's stack at the face floor keeps 4px from the top river's third row
on the shortest boxes), and the
phone's chrome scales from the river tile (the small chrome's px up to a 24px river tile, growing with
it past that, never under 40x40), except the decision controls, which keep their 40px rows. It gives
river and own tiles of 19 and 45px at 667x375 (its bars bound the river tile), 21 and 47px at the notch phone's
750x390, 23 and 44px at an iPhone 11's 808x414, and 24 and 45px at 932x430 (both bound by the side strips' line),
whatever the state shows, with centres of 114x90, 126x83, 138x91 and 144x96px (width by height).
With a browser's bars shown the boxes
give 18 and 36px at 891x331 (a 108x70 centre, its lanes beside the own row, where at the column's edges its band,
starting at the centre's left edge, would need three rows), 13 and 32px at 808x275 (100x69, its lanes beside the
own row), 10 and 34px at an iPhone 13's 750x251, and 7 and 32px at 667x236 (100x90, held there by the right seat's three pons). A desktop window short enough to use the phone layout follows the same solve: 28 and
53px at 1024x500.

The centre is a rectangle in every family, because one square side had to hold both the vertical room and six
river tiles and so held the river tile back: off a phone six river tiles wide by 4.5
tall (234x176px at 1280x720, room for the four scores, the round and the counts); on a phone its height is what is left above the own hand, at least 68px, its text's room, and its width six
river tiles and at least 100px. The core's side is
the centre plus eight river tiles, two gaps between the centre and the rivers (0.3 of a river tile on a phone, 0.15
off one, the top one past its rows' tile edge) and the top and bottom rivers' latest-discard gaps, so no river's latest discard stands past it, across each axis's
own side of the panel; the side rivers' wrapped fourth rows are reserved beside it, so the core is about 17.3
river tiles wide off a phone. Its corners, which the pinwheel leaves empty, hold the four plates and, off a phone,
the notices' toasts (bottom-left, under the left river's
longest reach); the decisions stand along the own row's top, from the bottom river's start over it to the right
river. A phone's play switches stand as a two-by-two block at
the left bar's foot, ending at the own row's top, and a replay's moves in the right bar, so a replay's board is the
live game's there too.
An opponent's concealed hand tile is the river tile; its drawn tile stands 0.15 of a river tile
apart on the top strip, and 0.35 on a side strip, where the 0.2 tile edge it shows lies in that gap.

| Relationship | Starting point | Derived (667x375 / 750x390 notch board / 1440x900) |
|---|---|---|
| Core height / play area height | 0.6 | 0.71 / 0.71 / 0.75 |
| Centre height / core height | 0.3 | 0.34 / 0.30 / 0.33 |
| Centre width / centre height (6/4.5 off a phone; on a phone its `w` / `c`: 114/90 and 126/83) | 1.2 | 1.27 / 1.51 / 1.33 |
| River tile width / own hand tile width | at most 0.75 on a phone (own at least 4/3 of river, at most a full hand within the board and, where any own tile allows it, a right bar that holds a replay's moves), 1/1.45 to 1/1.2 off it | 0.42 / 0.46 / 0.73 |
| Opponent hand tile width / river tile width | 1.0 | 1.0 / 1.0 / 1.0 |
| Opponent hand tile width / own hand tile width | at most 0.75 on a phone (own at least 4/3 of river, at most a full hand within the board and, where any own tile allows it, a right bar that holds a replay's moves), 1/1.45 to 1/1.2 off it | 0.42 / 0.46 / 0.73 |
| Own hand tile width / play area width | 0.05 | 0.067 / 0.063 / 0.046 |
| Own hand tile height / play area height | 0.15 | 0.160 / 0.161 / 0.100 |
| Gap between a river and the centre, in river tiles | 0.3 | 0.32 / 0.29 / 0.14 (0.15, rounded; the top river 0.53 / 0.52 / 0.34, past its rows' tile edge, a phone's taken from its centre's height, down to 1px under its least, only where the decisions' band keeps its place, never from a tile) |
| Gap between neighbouring rivers, in river tiles | 0.3 | 0.32 / 0.29 / 0.14 (0.15, rounded) |

A starting point is never a gate threshold. A derived value may become one, with a tolerance,
only where it protects the approved layout from a regression a player would notice.

The opponent's hand at the river tile follows Tenhou (every opponent hand and meld at exactly the
river tile, once a camera's depth
is taken out). Decision off a phone: every other hand and river reads at one size, and the own hand
at 1.2 to 1.45 of it (1.3 or more wherever the width allows), because the own row stands
between the side strips and a wider row widens the felt between them and the rivers; the own melds, at 1 river
tile, stand at 0.69 of the own tile at the cap. Only width ratios are
compared: Mahjong Soul's hand faces its camera over foreshortened rivers and Tenhou's view squashes heights. A phone keeps a larger own tile, which touch needs, solved
together with its river tile from the box, the own tile as large as a full hand within the board, the side
strips' lines and a replay's moves in the right bar allow above its 36x48 floor: 2.37 river tiles at the floor, 2.5 at
the notch phone and 2.86 at 932x430. A decision control's tiles stay inside
its row.

The starting points do not fit together at the 667x375 floor. The rule resolves it by the joint
solve: the core takes the height the own row leaves it, the controls standing in the bars and over the bottom
river rather than in a row of their own;
the two tiles are the largest pair the box holds above the own tile's 36x48 floor; and the centre's
share grows, its text following the centre down, so the round, the wall count and four winds with
their scores stay readable at the floor. At the floor this gives a core of 0.71 of the height, a
centre of 0.34 of the core (114 wide by 90px tall) and 19 and 45px tiles.

## States

- **The anchor**: the reference scenario *East 2, turn 10*. Every seat with 8 to 12 discards, one
  seat with a meld, one opponent in riichi, ordinary names, one AI player. Three checkpoints that
  cannot share a screenshot: the own turn with a drawn tile; a call offer on an opponent's discard
  with its countdown; the own riichi declaration (the toggle on, the declaring discards marked).
  Every visual review opens these.
- **The dense gates**: a twenty-discard river at every seat orientation; four melds a seat with every
  kan kind and every feeder position; five dora indicators; long names and away seats; a call at
  every seat; a triple ron's callouts; several offers at once, a chi with a choice; a turn in its
  bank; the dense round results (pao, nagashi mangan, double ron, a yakuman); the three switches
  on beside furiten at the floor viewport. They must stay
  legible, in order and owned; they are not what the board is designed around.
- **The sparse and the interrupted**: the first turn of a hand with its kyuushu offer; a
  first-turn win; a declared kan in its chankan window; a long notice; reconnecting; a lost seat;
  an AI standing in and the human returning; faces that did not load; an ended session.
- **The rest**: the seating over the first deal (its start confirm owed and sent) and at the game's end, the round
  results, the leave question, a long notice opened in its sheet, the rotate panel during an open decision, the
  replay controls and its loading, incomplete and damaged states.

## Viewports

Support tiers. Decision: the primary sizes are desktops at least 1100px wide, phones from 667x375 in
landscape; look trade-offs are decided for them. A narrower desktop window
(below about 1100px wide: 800x600, a laptop's split-screen half, a small browser window) is
best-effort: the geometry keeps it free of overlaps and every control reachable, but it gets no
tuning of its own; a bot's name may shorten in its badge there; its column is bound by the width and its bars
stand at their floor, the notices at their least text, the switches as letter chips and the cog in the board's
corner.

The reference is drawn, and every review opens, the same three: the 667x375 floor (iPhone SE), an
iPhone 13 in landscape with a notch's safe area (844x390 with side insets of 47 and 47; its 21px
bottom inset is ignored on a phone board), and 1440x900. The gate's automated matrix is its own, apart from these reference viewports. It selects
representative worst cases across the floor, 1440x900 and 2560x1440 (a large desktop, the chrome
a step up). Each further page/viewport combination exercises a distinct layout path or a denser
form not already covered. Other states run once where they bind, or are omitted when a kept case
covers the same elements and layout path in a harsher form. Its further viewports: the notch
phone, an iPhone 13 upright (the rotate panels),
1366x657 (a laptop's window, the shortest primary desktop, its decisions at the control floor in the narrowest
band), 800x600 (a narrow desktop, a phone's chrome on a desktop's geometry, its decisions over river tiles),
1280x720 and 1440x770 (just over the 760px from which the chrome grows), 700x540 and 900x600 (small windows, a
panel against the board's width), 1024x510 (a short tablet, wide but under a phone's height) and
680x375 and 700x375 (wider phones at the floor's height), an iPhone 11 full screen with its bars
collapsed (896x414 with side insets of 44, its 21px bottom inset ignored, so the board is 808x414),
and the phones as their browsers box the board with their bars shown, since every phone size above is a display and a browser's bars take a
third of its height in landscape until the swipe the board asks for collapses them: an iPhone 11 in
iOS 26 Safari (896x275 with 44px side insets, measured) and a Galaxy A25 in Android Chrome (891x331,
estimated from its toolbar and status bar). There the board lays out whole and tappable at the
own tile and river tile the phone solve gives (the river at the face floor or more where it fits: the A25's box gives 17px, the iPhone's 13px), and the box the collapsed bars leave is a display size above. The floor
display's Safari box (667x236) is pinned by the geometry's tests alone. The first release that reached
these boxes drew a 2px river tile. The composition is identical on all the landscape ones.

## Review checklist

A review opens each anchor checkpoint at the three viewports and answers, in writing:

1. Can a player see the four zones and tell every tile's owner at a glance?
2. Is the player's next task the most prominent thing on screen, and the table still scannable?
3. Is each seat's identity in the place the reference fixed for it, the same in every checkpoint: the four plates
   one rectangle in the core's corners, mirrored about the centre?
4. Do the rivers read as six-wide rows with space around each river and no two rivers touching?
5. Is there one strong cue for the seat in turn, is the latest discard found at a glance, and are
   the available actions ranked as above, with the two-step call's way back visible?
6. Are the decisions one cluster along the own row's top, the timer right of the
   pass, base and bank apart, in one row where the width holds it, clear of every opponent's tile, the own hand, the
   centre, the toasts and a phone's left bar, and drawn plainly on top of the own river's tiles under them?
7. Does the table read as one column, each side hand close to its river with no wide empty felt between
   them, and do the side bars hold only the controls and notices, never a tile?
8. Is every face readable, the riichi hand included, and is nothing clipped, hidden or overflowing?
9. Compared with the current board, is any information or interaction lost?
10. Are the play switches and the furiten mark read as on, off or absent at a glance, apart from
    the decisions and never mistaken for one?

A review that only reports "no check failed" has not reviewed. A review compares with this
document's composition for coherence and with the current board for regressions; a review of a
fix also inspects before and after, since a passing check cannot confirm that a visual problem
is gone.

## Automated checks and human judgement

The automated visual checks protect the measurable floor: no required information or control hidden,
clipped or overflowing (concealed faces, content that legitimately scrolls or sits behind a modal,
and a notice shown in whole lines with a "Show all" that opens the complete message are not
failures; neither is a river of 21 or more discards running under other elements, which no check builds, nor a desktop's
decisions over the own river), tap targets (40x40 for a button, a badge and a play switch, which
are controls; an own tile keeps the 32x42 floor on a phone, a safety limit; a desktop's own tile
follows the derived values and has no separate floor), readable faces and text sizes, text and marks
at a contrast of at least 4.5:1 against what they sit on (a held-back face included: it is greyed,
never darkened), no state told by colour alone (a switch's on state included; tile identity aside: a
red five is red and carries its own extra dot, which must stay visible at river scale), safe areas
respected, the rotate panel in a narrow portrait viewport, and, at the reference viewports, two
derived proportions held within a tolerance, the river tile over the own tile and each river's gap
from the centre, with neighbouring rivers no closer than that gap (a sparse river stands farther
from its neighbour); the opponent's hand at the river tile holds everywhere, and the other derived
values are review's, not the check's. On the tilted table the centre's size, the pinwheel's gaps and the face
floors are measured as laid, before the camera; the river tile over the own tile is measured as shown across the
core's middle, within the camera's 5% band; and the shown faces keep the same floors (a quarter pixel of rounding),
the rivers their 3px least to each other and to the tilted centre with each tile's edge drawn under it, and
a badge's pill keeps 4px off every tile on the table and its riichi stick 10px (6 on a phone). WebKit's pixels come from its compositor (a
software screenshot flattens the table's perspective). Clarity,
hierarchy and coherence are judged by the checklist
above. A visual failure that can be measured may earn a check; a judgement must not be turned into
an arbitrary pixel rule.
