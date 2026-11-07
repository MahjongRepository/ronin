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
- **Flat top-down.** No camera, no perspective. Depth comes from the surface, the tile's edge and
  its shadow. This keeps the client light and fast on low-end phones. Decision: one light for every
  seat, as Tenhou's: each tile's edge shows toward the screen's bottom (its ivory body over the
  back's layer) and its shadow falls down and to the right, whatever the seat; tiles lying together
  (a river, a meld, a hand that takes no input) share one edge and shadow under all their faces, so
  a tile nearer the screen's bottom covers the edge of the one behind it and no edge or shadow ever
  lies on a face. A chankan source's ring lies flat over the tiles.
  The own hand's tiles stand facing their player (Tenhou's): a band across each one's top.
- **Composed for ordinary play.** The design anchor is a mid-round state with real decisions on
  screen. Dense states (long rivers, four melds a seat, five dora indicators, long names) must
  stay legible and unambiguous but never reshape the ordinary composition. Exception: top and
  bottom third rows beyond nineteen discards may clip or extend under peripheral elements.
- **One composition on every screen.** Far seat at the top, side seats at the sides, identities in
  the same places, decisions by the hand, at the 667x375 floor, on a notch phone in landscape and
  on a desktop. Width changes how far apart things stand, never where they are.
- **The player's next task is the most prominent thing on screen.** At rest the hand dominates
  and the centre is one instrument; during an offer the offer leads; over a result the result
  leads. Table information stays scannable underneath. Colour marks an actionable or meaningful
  state, and tile identity (a red five), and nothing else.
- **Show what is known, never what is guessed.** The board draws the state the server supplied:
  no invented draw, no decremented wall, no deposited stick, no revealed indicator before the
  event that reveals it. A local countdown is an estimate; the server's move is the fact.
- **Table conventions are followed, not reinvented.** Rivers, melds, the sideways tiles, the
  separated drawn tile and the riichi stick look the way riichi players already read them.
- **The live game is landscape only.** Its play area is the safe area of the landscape viewport,
  kept at least 10px off each screen edge on every board that is not a phone's so no tile meets a
  border, at whatever aspect ratio it has; nothing is letterboxed. Whether the board is a phone's is
  decided once, from the box the page would give it with that 10px gutter (the safe area kept), so
  the gutter never changes it. A portrait viewport narrower than 600px sees the rotate panel instead
  of play, regardless of touch or mouse input. It asks the player to rotate the device or widen the
  window and says that play and its timers go on. A replay or a storybook page may be read upright and scrolls
  instead.

## Composition (decisions)

```
+-------------------------------------------------------------------+
|  top strip (backs) ............................     |   settings  |
| |   [dora]    |               [top badge]            |             |
| | [left badge]|                                      | [right badge]|
| left strip    |          [ top river ]               | right strip |
|               |  [L river]  [centre]  [R river]      |             |
|               |          [ bottom river ]            |             |
|  switches     |                   decisions   timer  |             |
|              [own badge] [furiten]                                |
|              [ OWN HAND ...................... ] [melds]          |
+-------------------------------------------------------------------+
```

The diagram is illustrative: it shows the three rings and the zones, not exact placements.

Four seat zones, top, left, right and bottom, are made perceptible on the surface. Decision: four
faint seams pressed into the felt (a groove over a lip) from the centre panel's corners, the upper two to the play area's top corners, the lower
two to its sides at the top of the foreground band, so the whole foreground is the viewer's own; the
side fields carry a faint tint. They establish perceived ownership; they are not clipping
boundaries, and a long river may cross one. A seat's tiles and the score data facing it are oriented
toward that seat as on a real table: the top seat's tiles upside down, a side seat's on their side,
every river reading left to right from its own seat. Names, notices, callouts and controls stay
upright. The walls are not drawn; the wall count in the centre and the indicator slots stand for
them. The cost is the spatial picture: how much wall is left and where the dead wall sits are read
as a number, not seen, so emphasis on the count as the wall runs out is a candidate.

- **Core**: the centre and the four rivers. Compact, centred, sized primarily by the play area's
  height and bounded by the width left beside the perimeter on a narrow landscape area. It does
  not grow with spare width.
- **Perimeter**: each opponent's strip and its badge, in its zone toward the play area's own
  edge. On a wide screen the side strips stand away from the core and the surface between them is
  intentional space, not a gap to fill.
- **Foreground**: the own hand, its badge and melds, the decisions and timer by it, the play
  switches and the furiten mark, over the bottom of the play area.

## Elements

- **Surface.** Fills the viewport, under the safe-area insets too, while the content keeps to the
  play area. Decision: a petrol felt in the dark teal family, lit over the core and falling off
  toward the edges, with a fine static grain as its only texture (felt at full size, gone in a
  thumbnail: no weave, motif or wear) and the zone device; nothing else is drawn on it. Ivory faces
  separate from it by value, the ochre backs by hue. The grain is one small repeating image under
  the gradient: no runtime noise, filter or blend mode, so a low-end phone paints it once.
- **Centre.** Decision: one square panel, each seat's wind and
  score on the side facing it, turned to that seat and close to its edge, and in the middle the
  round name large (East 1, South 4, a West round when the game runs on) over one line of the wall
  count, the honba and the riichi sticks on the table. Each side reads wind then score, all four at
  the same emphasis, tabular digits: the wind a quiet letter, the dealer's (East) on a muted red chip,
  as Mahjong Soul and Riichi City mark it in red; the score in hundreds with its last two digits
  smaller and quieter (`250` `00`), as Tenhou draws it. Every layout keeps each side at least as long
  as a normal six-tile discard row, fitting the centre and tiles together.
  The rivers keep its corners. Score rows offset toward their seat's right like the rivers'
  pinwheel, so a long row never meets the next
  side's. The counts keep one line, a narrow centre's at a smaller size; where even the floor's
  size cannot hold them, the wall count takes a line of its own and the honba and riichi sticks stay
  together on the next. While a badge is pinned, the wall count stays and a label in the round's
  place names whose differences show: the seat's whole name on one line where it fits at a readable
  size, never shortened or broken, else the seat's wind; the honba and stick counts step aside for
  it. One primary cue on the centre for the seat in turn: Tenhou's green bar along that seat's whole
  edge of the panel, its corners included, a shape the riichi stick never takes. Convention: a seat's
  accepted riichi stick lies on its side of the centre, as on a real table; this is where an
  established riichi is read, and the seat's badge only repeats it quietly. Decision: the stick, a
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
  but visible gap separates a river from the centre and from its neighbours; tiles touch inside a
  river, rivers never touch each other. Decision, departing from the run-on convention for side
  rivers only: at the 24-tile capacity a side river wraps its overflow into a fourth row of six
  toward its seat's edge, since a third row running on along a phone's short side would cross the
  hand; a top or bottom river keeps the convention, its third row running on along its line to
  twelve tiles. Layout reserves nineteen discards: two rows of six and a third of seven, including
  a sideways riichi tile and the latest-discard gap: 7px across the light, and along it (a side
  river's from the tile before, a top or bottom river's from the row before) deeper by the 0.13
  tile edge that falls into it, so every seat's reads as one gap; a phone keeps 7px along it too,
  its edge two pixels and the reserve a pixel of its river tile at the floor.
  Rarer, longer top and bottom third rows still
  render in full but may extend under peripheral elements or clip at the board edge; they do not
  shrink tiles or move controls to reserve their full length. Every row reads left to right from its seat, so the river reads in order and as its
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
- **Opponent strips.** In the zone toward its edge, at the river tile's scale: tile backs in live
  play, the faces the mode reveals in a replay or a revealed result, in the same place either way;
  the drawn tile set apart by a short gap only where the supplied state identifies one (a replay, a
  revealed hand, a live draw the server announced); a reconnect's snapshot cannot tell a held draw
  from the discard a call leaves owed (both leave 3n+2 tiles), so after one no gap is drawn until the
  seat's next draw; the seat's melds at river scale at the strip's far end (the
  hand's right, from the seat's view), as the own row's, so a call moves neither the hand nor the melds already laid. The strip is not a turn cue. Invariant: a strip stands apart from its own
  river, backs or faces, so that neither reads as a row of the other. Decision: a concealed hand,
  backs or faces, is 3:4 at the river tile's size (Tenhou's and Mahjong Soul's ratio), so an
  opponent's hand reads as plainly as its river. Decision: a concealed tile stands on its edge,
  drawn as its top seen from above (Tenhou's side seats draw it in profile): half its 3:4 slot,
  at its owner's edge, ivory toward its owner and the back's colour toward the centre, so a live
  hand never reads as face-down tiles (a closed kan's ends, the unrevealed indicators); the slot is
  kept whole, so a reveal shows the faces in the same place. Decision: a hand's tiles stand a
  one-pixel hairline apart, as the own hand's; a side strip's tiles run along the light, so the
  tile edge would fill that hairline, and the table's colour is drawn into it instead; a side
  strip's drawn gap shows that edge under the tile the light lays it on and is deeper by it, so
  the clear table past the edge reads as the top strip's gap. Every seat
  keeps its melds in one continuous line to the hand's right from that player's view: downward for the left seat, upward for the right. The oldest meld stays at the far end;
  newer melds join toward the hand. Melds never wrap beside the hand or into parallel columns.
  All melds in a strip scale together to fit, never below the 13x17 face floor, beside the hand at its
  fullest with a drawn tile set apart, so a draw never resizes them. The side lanes keep
  their existing buffer before interior controls as the melds scale inside the edge line. The side layout
  clears the reserved badge, play switches and own row using each meld's actual footprint.
  Each top meld stays above what it keeps clear of there, its tiles one size, scaling only where
  its line cannot hold them at the river tile. Decision: a side strip reserves the larger of a
  full concealed hand and a hand with up to four kans at the meld face floor. That reach has one fixed place per viewport, never read from the
  tiles held, and nothing else stands in it. Decision: each hand's full
  reach stands centred on its side (the side hands on the core's height) as far as its limits below
  allow, so a hand holding fewer tiles fills its reach from its start. Off a phone, the left hand's
  reach is centred where it fits between the top strip and the switches (or the band); else, and on a
  phone, it runs down from under the top strip's depth, and the play switches step in past its
  strip's stacked depth where it would meet them, so every meld runs on beside them (on a short
  desktop whose centre cannot narrow for that, past a tile-high line only, a stacked meld then ending
  above them).
  The right hand's reach is centred where it fits between the top margin and the band's top, else
  it runs up from the band's top; where its full reach would then enter the band (a short desktop,
  the 667x375 floor), it runs from the top margin across the band, whose row then ends before it (on a
  phone, ending above the own row). Upright, its reach is centred where it stays under the top badge's
  pill with its badge over it, else it ends before the band's top. The right strip's melds run to the
  top margin, under the page's corner (upright, to under the top strip's depth, which may reach over it).
  The top strip's line runs from the left margin, the counters standing under it, and its hand's full
  reach stands centred, moved right as far as its badge's lane under it needs, short of the board's
  edge by a badge gap; its melds stay above that badge where they reach its lane (a
  limit that counts the melds at river scale, or the hand without its drawn tile, so a draw never moves it), within the
  room the whole hand leaves.
  Upright, a dense top strip (its melds at the face floor) starts further right instead, up to the board's edge,
  its badge staying where it is.
- **Badges.** One fixed shape for every opponent: the name on its first line and its quiet marks on a
  second, an AI player, a human seat an AI stands in for (the human identity kept, the mark cleared
  when they return), riichi as a small stick lying across, and disconnected; the name's line fixed whether marks show or
  not, the pill one line tall without marks and growing down for their line into the badge's reserved height, so
  nothing around it moves; the own badge alone keeps one line, its marks after the
  name, its lane being wide and short. Each has a fixed place in its zone outside the rivers, the same
  in every state at a given viewport and viewpoint; a badge's place never depends on how many tiles
  the seat holds. Decision: in landscape the side badges are their strips' headers, mirrored at one
  height (a phone's right one lower) beside each strip's reserved depth, a card's width at most and clear of the top river's
  reserved seven-tile third row by a river tile, so neither reads as that river's label: under the counters,
  and on a desktop whose band stands below the core a step lower, 8px under the top badge's
  pill, so the opponents' names never read as one row; where that place leaves less than an
  ordinary name's lane beside that third row, below it by a river tile instead. A short
  desktop takes that step only where the decisions' tallest column (five offers over the band's
  control and the timer) leaves room under the right one, else keeps them under the counters. A
  phone keeps the left badge there and steps the right one, which stands beside
  the top badge, 6px under that badge's pill, the decisions' column starting under it. The top badge mirrors the own one through the centre, under the top
  hand's first tile toward the table, a river tile's edge and 6px below the hand's line so a meld
  over it keeps a gap, ending where the hand ends, its lane from half a river tile past the top
  river's end at least an ordinary name wide where the board allows; the right badge stays
  right of the top hand's end. The own badge heads its hand, above the hand's first tile and any added kan's rise, under the play
  switches, which stand that much higher (a narrow desktop's band row with them); where the switches' end leaves it
  less than an ordinary name's lane (an ultrawide desktop's hand starts near or past it), its lane is its own, short of
  the bottom river, and the decisions' row starts past it. An upright board
  keeps that template as far as its geometry allows: the own badge above its hand's left end, under
  the decisions' rows, the hand centred in the width its tile leaves; the top badge under the top
  hand's end, under the top strip as the counters, its lane clear of them where they stand level with
  it. Its top zone spans the whole width over the core, so a side
  badge there reads as the top seat's: the right badge stands in its own zone instead, right over its
  hand's reach, under the top badge's pill, short of the centre's column by half a river tile. The
  left badge stands toward the table from its hand, under the counters,
  as in landscape: a card wide where it stands over the core, else short of the top river's longest
  third row (a near-square board's core rises beside it) but an ordinary name wide at least, which
  only a third row past six tiles and a riichi tile reaches (a rare overlap, accepted).
  A long name is shortened in the middle so its end, which tells AI players apart, stays. Decision:
  the badge carries no wind or score; the centre holds every seat's score, and hovering or tapping a badge
  shows the other seats' scores in the centre as differences from it, labelled as that seat's
  differences (kept from the current board); hovering the centre does the same for the bottom seat's
  badge, as Tenhou's. The badge is therefore a control: its tap area meets
  the control floor whatever the drawn badge's size, a key activates it like a tap, a tap pins the
  differences, and tapping it again, tapping elsewhere or Escape returns the totals; a pinned badge
  shows a faint 1px inset ring on a slightly lighter plate, quieter than the turn cue, and a focused one the accent's outline. The name
  shows on every board, upright ones included, shortened rather than dropped.
- **Dora indicators.** The five dora indicator slots (each indicator as a face once the event
  that reveals it has arrived, the rest unreadable backs; indicators are not the bonus tiles), in
  the top-left corner under the top strip's line, from the left badge's edge and directly over it (6px
  apart), clear of the left strip, whose hand runs up past it to under the top strip. Where the top
  river's longest third row reaches it (a run-on row a real game rarely lays) the box may overlap it,
  a rare overlap, accepted.
  The honba and riichi-stick counts are the centre's, under the round, as Tenhou shows them; the
  corner does not repeat them.
- **Own hand.** Sorted, from its full reach's fixed start, the drawn tile set apart by a gap at the
  right; the melds stand at the row's right end by the board's edge, as on a table, never larger than
  its tiles. Decision: the melds take 1.2 river tiles, never past the hand's, where the row holds them
  beside the hand at its fullest (its drawn tile and gap counted), else shrink together to fit, never
  under the face floor. Invariant: for one viewport and one set of melds, no draw, discard, offer,
  riichi or callout changes a table tile's size, the hand's start or a laid meld's place; tiles still
  enter, leave, sort, rotate and take their drawn, latest-discard and selection offsets. Only a call
  or a kan refits the melds, inside their fixed room. Decision: its tiles are
  the play area's largest: on a phone for touch; off a phone (a desktop, an upright board) 1.6 of the
  tile every other hand and river shares, never under 4/3 of it, as far as its family's caps allow; after a pon or chi
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
  are presented as equals. Decision: a win is larger and ringed; on a phone it takes a row of its
  own above the calls. The controls show exactly the offer the server made and vanish as soon as
  the player or a play switch answers it. Pass dismisses them silently; a declaration immediately
  shows its callout and plays its voice, while the table waits for the server to resolve the action.
  Decision: a call with a choice of tiles (which chi, which tile to kan) is
  taken in two steps, the call, then the tiles, with a way to go back, and an illegal combination is
  never selectable; the first step shows one control per kind, and at the second the choices are the
  controls, in the controls' place, each a tile group drawn as the meld will lie (the called tile
  turned toward its feeder, a closed kan's ends face down, an added kan's added tile stacked), with
  Back in the place of Pass. Riichi is a toggle that marks the discards that declare it on the hand
  and greys out the rest; it can be untoggled until the discard is sent, not after. An expired
  decision stays visible and looks different from an open one; expiry is the client's
  estimate, and the server's resulting move (a timeout's discard or pass) is shown when it arrives.
  After a reconnect the open decision resumes with its remaining time, never a fresh one, and no
  stale selection survives. Decision: on a desktop the controls and the timer after them stand in
  one row ending at the hand's right end, its drawn tile included; on a short desktop, whose core
  shares the band's corners, the row starts past the bottom river's reserved reach, ending past the
  hand's end where that leaves less than a wide control (short of the right strip's reserved
  depth), and the higher-ranked controls stand
  above the band's control and the timer (the band's control too where the row cannot hold it
  beside the timer), clear of the right strip's deepest reach. On a phone the lowest-ranked
  controls, pass last, and the timer float in the gap between the bottom river and the hand instead
  of owning a foreground row, and never reach past the own river's reserved edge (a sideways riichi
  tile counted): at the band's right end, past the bottom and right rivers' reserved reach, the
  row stepping in past the right hand where it runs across the band; the rest rise in rank order,
  right-aligned, between the right river's capacity edge and the right strip's deepest reach,
  pairing up before they would reach the side badge; at the first step a pair may shed its tile
  previews to fit, since the action source shows the tile, while the second step's groups always
  keep their tiles. Every control keeps visible space around its label and its choice tiles, the
  longest label at the floor viewport included; a target that meets the size floor with its text
  touching its border has failed.
- **Input.** The contract the current board has, kept: a tile of the own hand is a button; one tap,
  click, Enter or Space on a selectable tile sends it, with no separate confirm step, and a tile
  that is not selectable takes the press and does nothing. A decision control sends on one press,
  except the riichi toggle and the first step of a two-step call, which only change what the next
  press means and are undone by pressing them again, by the way back or by Escape. A play switch is
  a board control, not a decision control: pressing it changes what the client answers from then on
  and sends nothing itself. Focus stays in the hand through a turn, and an offer's controls are
  reached from it without the focus being moved for the player. An expired decision still takes one
  answer, since the server alone decides by the wait whether it counts; an answer the server refuses
  while the wait goes on reopens the decision as answerable, with the refusal as a notice. Decision:
  one press is the only input; there is no touch confirm step (select, then confirm), as a default
  or as a preference, since its second gesture costs time on every turn and the own tile already
  exceeds the phone's tap floor.
- **Timer.** The countdown beside the decision controls as large digits, the base time and the bank
  apart (`5 +20`), the bank marked while it alone is draining, so a player always knows which time
  is being spent. Decision: a slot of fixed size and place, a caption line over the digits (time up,
  bank), so expiry and the bank never move it or the controls. Answering dismisses the timer with
  the controls; there is no submitted caption or checkmark. It is the viewer's
  own: it shows for the viewer's open decision and round confirm only; the server sends no other
  seat's time, and none is drawn.
- **Turn cue.** One primary cue for the seat in turn, Tenhou's green bar along its side of the
  centre's edge, and one quiet reinforcement on its badge, a bar in the same green along the badge's
  bottom edge on every seat, neither in the accent; no further turn decoration: the
  current board's "Your turn" and "Your call" labels and the line under the hand are decoration and
  go. Selectable tiles, the latest discard and the decision controls keep their own states, which
  are information, not decoration.
- **Furiten.** A small neutral status label (a dot and the word) beside the own badge, above the
  hand's left end, taking no room in the row so the hand never moves, not a button-shaped object and no prohibition sign, shown while the supplied
  state says the seat is furiten of any kind and cleared when it says so no longer; it gives no
  reason the state did not supply and never implies tsumo is unavailable.
- **Play switches.** Three toggles with one fixed place in the foreground, on the hand's side away
  from the decisions, clear of the left hand's full reach, answering for the player while on:
  *Auto win* takes a tsumo offer at once and a ron offer at once (decision: no pause, since the callout and the result show the claim and its
  feeder); *No calls* passes a call prompt that offers chi, pon or open kan and no ron, before its
  controls show, and never touches the viewer's own turn (closed kan, added kan, riichi, tsumo and
  kyuushu stay offered); *Auto discard* discards the drawn tile at once on a turn that offers
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
  This goes against the precedents for Auto win (Tenhou's manual clears only its no-call every hand
  and its auto-discard when the mouse was touched; Mahjong Soul players ask for auto-win to
  persist): one rule for all three switches, and no win taken on a later hand the player might have
  declined. They survive a reconnect within the hand in the mounted client; a reload or a new tab
  starts with them off. They are the client's standing answers, taken exactly where the player's
  press would be, with the decision's wait id, so the server, which keeps no preference, sees an
  ordinary answer; the latest-discard mark and the table are unchanged by an automatic pass, and an
  automatic discard travels like a pressed one. Decision: Mahjong Soul's compact strip, a square
  chip per switch showing its letter (A, C, D in English; each language picks its own) and a button
  after them that shows each letter's name over the strip until pressed again, so a player
  understands them without a manual; the name is each chip's tooltip and its accessible name too.
  Each switch shows on and off apart, not by colour alone (the established clients use grey against
  green): filled with a bar under the letter, or empty with a ring. Each chip meets the control
  floor; a switch is reached from the hand's focus like a decision control. Not on a replay board;
  the decisions stories show them, on and off. On an upright board, the chips keep a horizontal row
  above the own badge and hand, with 40px targets. Pass and the timer stand to their right; extra
  offers wrap above, clear of the right strip.
  The own hand and core keep their sizes and places; the left melds end above the switches.
  The names open above the row. A visible live board never hides the switches
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
  120ms, with a faint trail. The latest discard settles into its river slot in 120ms when its mark ends.
  A travelling tile keeps its body and shadow throughout, with size, orientation and the own hand's top band
  changing continuously from source to destination. Light stays fixed to the screen. Rearranging hands, settling
  discards and moving or resizing laid melds animate their actual tile wrappers inside their group, retaining its
  shared edge and shadow and native button feedback. Meld resizing keeps its tiles moving and scaling together
  under that shared shadow. A discard still changing size or orientation in flight finishes as a travelling tile.
  The hand closes gaps and sorts over 200ms after the discard's flight, with an additional 300ms pause in live play.
  Replay settles the previous stop's tile movements before measuring the next move, so rapid stepping animates
  only the latest move and never waits for an animation backlog. Calls assemble their
  meld from the original hand and river positions; travel time follows distance at the local tile scale, bounded
  to 80–300ms. Starting hands and indicator slots appear immediately at each deal. There is no drawn wall.
  Opponents' revealed hands replace their standing backs one tile every 30ms, without a flip; waiting backs stay
  in their native hand slots, retaining the hand's shared shadow and the side hands' gaps. The hand stays
  automatically sorted and keeps its existing hover and selection feedback. Motion never blocks input, delays
  game state or invents a hidden tile identity; later events preserve unaffected movements. A fresh page,
  reconnect, replay jump or viewpoint change shows the requested position immediately. Reduced motion disables
  tile travel and staged reveals. Match standings fade in over 1.5 seconds and fade away over 250ms when dismissed;
  round-result panels, their opening delay and their yaku presentation are unchanged.
- **Page corner.** A settings cog, small, in one corner. In landscape it sits in the free space
  inside the right strip's deepest reach, with a gap so its whole tap target clears the melds;
  where the top hand leaves too little room, it sits below the top strip and badge instead.
  Upright it stays at the top right. The icon is smaller than its control-floor tap target.
  It reserves no room in the strips, hands or badges, which keep their places; a
  panel may cover it. Decision: its menu holds the sound switch, a language row (one compact strip of the
  three languages by their native names, the current one marked), then the
  connection status (a dot and its whole label); a tap outside the menu only closes it, and Escape closes it back to
  the cog. While the status has a word to say (a drop, an end), the cog carries a dot in the status's tone, so a drop
  shows without opening the menu. A replay has the same corner and cog, its menu the sound switch and the language row alone. The live
  board has no way back of its own; the rotate panel in a narrow portrait viewport keeps
  one, which asks the leave question, and an end's panel offers the lobby.
- **Sound.** The live game plays an original synthesized resin tile clack and a soft two-note countdown tone,
  plus a soft 180 ms chime once for each newly seen decision offering chi, pon, kan, ron or tsumo that still needs
  the player's answer. A previously seen prompt repeated or reconnected, a refused answer reopening, an automatic answer and a
  turn offering only a discard, riichi or kyuushu do not chime. The decision chime is live-only. The supplied
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
  faces that did not load: decision, their one place is the left zone's open field under the left
  badge, beside the left strip and outside every river's reserved reach, which a panel leaves free, so an
  automatic notice covers no tile within its reserved reach, badge, control or panel (the accepted
  overflow of top and bottom third rows beyond nineteen discards may extend under it); worded for a player, and a recoverable
  interruption looks different from an end. Several stack there, ongoing conditions first; in a
  replay an incomplete recording's note takes the place, under any notice; it stands above a panel's
  dimming. A notice never loses its ending silently: one taller than its place shows whole lines and a
  "Show all" control, which opens the whole message in a sheet. Decision (step 4.2): "Show all" is the
  clamped notice's last line and the whole notice its target (at least 40px high); where even one
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
  announcement). At the primary sizes every panel, a round result included, fits whole; a board too
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
  browser needs before the game's sounds play. A replay opens on the seating with a Start in the OK's place, and off
  a phone's short board the replay's seating (start and end) covers the table's centre block, its text scaled to the
  block.
  Decision (placements drawn in step 4.1): the notices' field is reserved whether or not a notice shows, so a
  panel's box and its tile size never change as a notice comes or goes. On a desktop a panel stands centred,
  starting past the left river's reach; on a narrow desktop (narrower than `$small-chrome-width`) it stands
  between the side strips, past the left river's reach; on a phone it stands at the top, its notices beside it; on
  an upright board, at the top and above the notices' place. A desktop's panel fits its content whole.
- **Round result.** Decision (the established clients order it differently; Tenhou's viewer puts
  the total first): the winner and how (ron, and from whom; tsumo; a head bump names who lost the
  ron); the winning hand with the winning tile set apart and its melds in their shape; the yaku,
  with han where han are meaningful and yakuman names and multipliers where they are; the dora,
  red and ura counts apart, the ura indicators only for a riichi winner and per winner in a double
  ron, both kinds in a column of their own beside the value, under one small "Indicators" caption,
  so they never read as the dora; the total (han and fu where meaningful, the limit name, the
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
  for tenhou, the earlier seats' first discards for chiihou.
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
  floor viewport. Decision: no narration and no visible position line; the board itself shows each
  move and its centre the round, and the position (round, step) is read out to assistive technology
  only. Its calls are read out as the live board's are, silent while the reader scrubs (see
  Notices). Decision: the controls take the foreground band outside the own river's reserved reach
  as one group in the decisions' place, standing as live's decisions do (right-aligned in it, ending
  at the hand's end unless the place reaches past it to hold the group), the moves before the
  options; the own badge heads its hand alone at the band's left with live's lane, nothing over it
  (the switches' place stays empty). Where the band shares the core's corners (a phone, a short desktop)
  the group does not fit beside the rivers' reach: the moves keep the switches' place and the
  options the decisions', on a phone filling the live slots of its composition: the moves in the
  switches' one-row place, the options at the band's right end. Upright, the group stands in the own badge's row, short of the right
  strip's deepest reach, where it leaves that badge an ordinary name's lane, else right-aligned in
  rows over it, the options over the moves. The status (an incomplete recording's note) takes the
  notices' place, under any notice. Decision: the moves are a round
  back, a step back, play (in the accent, the player's own action), a step on and a round on, with
  either end too on a desktop's chrome (elsewhere the round list's
  first row and its foot, Last step, always in view, reach them by touch); the options are hide hands and
  the round list, the switch over the round list's toggle where the band holds fewer than two, the
  toggle in the band. Decision: autoplay has one pace, no speed control. Decision: the viewpoint has no
  control of its own: pressing another seat's badge, or its score in the centre, views from that seat,
  so a replay's badge pins no differences (hovering still shows them). A panel over a replay's board never covers the controls, so the replay
  always moves on. Decision, a panel-only exception: on a board smaller than a desktop's chrome a panel
  takes all but the moves' row, the options hide but the round list's toggle, and an incomplete
  recording's "Ends here" stands between them, compact (before the group where they share a row;
  upright, in the row over the group's), and the panel's
  tiles keep their size, its content scrolling with its pager and action in reach. The options return
  as the panel closes. Loading, not found, incomplete
  and damaged replays each say so, as does a replay that cannot be drawn at a later stop (the failure
  screen); an incomplete one shows no result for its unfinished round.
- **Material and type.** Ivory tile faces with room around the glyph and a soft bevel lit from the
  screen's top, a small consistent two-tone edge and shadow; a red five reads as red at every scale, in a river, a meld, a revealed hand and a result;
  backs in one colour, the canonical yellow-orange: an ochre plastic, darker and less luminous than
  the accent so a strip of backs never reads as a control, its darker shade the back's layer under
  every tile's ivory body. Decision: the face artwork (the committed SVG set) stays; the room
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
and then it takes no gutter; anything else is a desktop, with the gutter, and a desktop under 760 px
high and at least 1100 px wide (a laptop's browser window) is a short desktop; the short desktop and
the chrome tiers (small under 1100 px wide or 520 px high, large from 2000x1200) are read from the
padded box. An upright board stays upright. Deliberately, a board 520 to 539 px tall without its
gutter can be a phone (always so when the safe area has no top or bottom inset, since the gutter
adds only what exceeds the safe inset), and a phone always has the small chrome.
On a phone both tiles are solved together from the box: the river tile the largest that fits, then
the own hand tile the largest that fits with it, at most as wide as lets a full hand's row stand clear
of both side strips' stacked depth and at least 4/3 of the river tile, a larger river tile waiting for
an own tile that keeps that share, but never under 36x48, the floor winning where both cannot hold. A
pair fits only where the decisions' place, from under the right badge down to the band's bottom, holds
the worst offers: a win over two rows of paired calls and the band's row, 182px at the small chrome.
The band's controls float in the gap above the hand, the gap below the top strip is 6px, and the
phone's chrome scales from the river tile (the small chrome's px up to a 24px river tile, growing with
it past that, never under 40x40), except the decision controls, which keep their 40px rows. It gives
river and own tiles of 17 and 39px at 667x375, 16 and 37px at the notch phone's 750x369 (where the
decisions' place binds), 18 and 41px at 844x390, and 21 and 45px at 932x430, whatever the state
shows, with centres of 114, 126, 122 and 126px: the larger own tile costs 844x390 3px and 932x430 9px
of centre in every state. A desktop window short enough to use the phone layout follows the same
solve; the river-first order has its price at 1024x500, where a 26px river tile takes a 37px own
tile. Off a phone the own hand tile is 1.6 of the river tile, never under 4/3 of it, and otherwise at most its
family's caps: on a desktop min(0.05 of the width, 0.1 of the height) and what a full hand's row holds, on an upright
board 0.1 of the height and the row, with no share of the width. On a desktop the river tile is the
largest whole-pixel size that fits with a centre six river tiles tall, the own row it sizes and
the top and bottom rivers' latest-discard gaps. The gap below the top strip uses the badge gap
instead of the former 40px separation, reclaiming height before reducing tiles. A desktop's band keeps a 48px control row
12px above the own row, and a short desktop's core stands 24px above the own row. Short desktops
also keep the centre and bottom river clear of the switches and replay moves. Upright boards
fit a centre at least six river tiles and 100px across. A phone's centre is at least six river tiles
and 94px across, its text's room, and fills the height left above
the own hand as far as the side fields allow: the notices' place 7.5 of its ems wide beside the left
strip's deepest reach, the decisions' column two controls wide beside the right one's, and the left
badge an ordinary name's lane beside the top river's reserved seven-tile third row. The core's side is
the centre plus eight river tiles, two gaps of 0.3 of a river tile and the top and bottom rivers'
latest-discard gaps, so no river's latest discard stands past it. The centre is square in every
family. On a short desktop its bottom river, from the centre's left corner, stays 8px clear of the
play switches. On a desktop the core stands above the
foreground band, its side at most 0.74 of the height. On a phone and a short desktop the core uses
the height between the top strip's slot and the own hand, and the foreground band shares its lower
corners, which the pinwheel leaves empty, its controls kept outside every river's reserved reach. A
short desktop's core ends its left river's capacity above the play switches, which stand over the
own badge's lane, centred in its room only as far as that allows. On a short desktop that place is
as tall as the play switches or the replay's moves (which stand there where the band shares the
core's corners), whichever is taller, so a replay's board is the live game's. A phone's place is
one row as tall as a control and as wide as the replay's five moves, stepped in past the left
strip's stacked depth over the own badge; its left river's capacity ends above the own badge, and
above that place too where the centre is too wide for the river to pass beside it, so a replay's
board is the live game's there too.
An opponent's concealed hand tile is the river tile; its drawn tile stands 0.15 of a river tile
apart on the top strip, and 0.28 on a side strip, where the 0.13 tile edge it shows lies in that gap.

| Relationship | Starting point | Derived (667x375 / 750x369 notch safe area / 1440x900) |
|---|---|---|
| Core height / play area height | 0.6 | 0.73 / 0.75 / 0.68 |
| Centre side / core height | 0.3 | 0.42 / 0.45 / 0.39 |
| Centre width / centre side | 1.0 | 1.0 / 1.0 / 1.0 |
| River tile width / own hand tile width | at most 0.75 on a phone (own at least 4/3 of river, at most a full hand clear of the strips and the offers' stack in its place), about 0.63 off it | 0.44 / 0.43 / 0.63 |
| Opponent hand tile width / river tile width | 1.0 | 1.0 / 1.0 / 1.0 |
| Opponent hand tile width / own hand tile width | at most 0.75 on a phone (own at least 4/3 of river, at most a full hand clear of the strips and the offers' stack in its place), about 0.63 off it | 0.44 / 0.43 / 0.63 |
| Own hand tile width / play area width | 0.05 | 0.058 / 0.049 / 0.044 |
| Own hand tile height / play area height | 0.15 | 0.139 / 0.134 / 0.094 |
| Gap between a river and the centre, in river tiles | 0.3 | 0.29 / 0.31 / 0.31 (0.3, rounded) |
| Gap between neighbouring rivers, in river tiles | 0.3 | 0.29 / 0.31 / 0.31 (0.3, rounded) |

A starting point is never a gate threshold. A derived value may become one, with a tolerance,
only where it protects the approved layout from a regression a player would notice.

The opponent's hand at the river tile follows Tenhou (every opponent hand and meld at exactly the
river tile, its own hand 1.44 of it on a desktop) and Mahjong Soul (the same, once its camera's depth
is taken out). Decision off a phone: every other hand and river reads at one size, and the own hand
at 1.6 of it, as both references draw it by width (Mahjong Soul's desktop 1.58 to 1.62, Tenhou's tablet 1.59 to
1.67); the own melds, at 1.2 river tiles, stand at 0.76 of the own tile, Mahjong Soul's 0.74. Only width ratios are
compared: Mahjong Soul's hand faces its camera over foreshortened rivers and Tenhou's view squashes heights. A phone keeps a larger own tile, which touch needs, solved
together with its river tile from the box, the own tile as large as a full hand clear of the side
strips and the decisions' place allow above its 36x48 floor: 2.29 river tiles at the floor, 2.31 at
the notch phone and 2.14 at 932x430. A decision control's tiles stay inside
the room the band keeps for its row, so a large board's controls never reach the bottom river.

The starting points do not fit together at the 667x375 floor. The rule resolves it by the joint
solve: the core takes the height the foreground band leaves it by sharing the core's lower corners,
where the pinwheel leaves them empty, with the band's controls floating in the gap above the hand;
the two tiles are the largest pair the box holds above the own tile's 36x48 floor; and the centre's
share grows, its text following the centre down, so the round, the wall count and four winds with
their scores stay readable at the floor. At the floor this gives a core of 0.73 of the height, a
centre of 0.42 of the core (114px square, its scores 14px) and 17 and 39px tiles.

## States

- **The anchor**: the reference scenario *East 2, turn 10*. Every seat with 8 to 12 discards, one
  seat with a meld, one opponent in riichi, ordinary names, one AI player. Three checkpoints that
  cannot share a screenshot: the own turn with a drawn tile; a call offer on an opponent's discard
  with its countdown; the own riichi declaration (the toggle on, the declaring discards marked).
  Every visual review opens these.
- **The dense gates**: a 24-tile river at every seat orientation; four melds a seat with every
  kan kind and every feeder position; five dora indicators; long names and AI marks; a call at
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
landscape, and upright windows; look trade-offs are decided for them. A narrower desktop window
(below about 1100px wide: 800x600, a laptop's split-screen half, a small browser window) is
best-effort: the geometry keeps it free of overlaps and every control reachable, but it gets no
tuning of its own; there, past the deepest left strip, the notices' place may fall under its 7.5
ems, and on a near-4:3 one (800 to 830x705, 1060 to 1090x880) the own row starts inside the left
strip's stacked depth, so a stacked left meld ends above the switches and the left melds still move
up when the first one arrives.

The reference is drawn, and every review opens, the same three: the 667x375 floor (iPhone SE), an
iPhone 13 in landscape with a notch's safe area (844x390 with insets of 47, 47 and 21), and
1440x900. The gate's automated matrix is its own, apart from these reference viewports. It selects
representative worst cases across the floor, 1440x900 and 2560x1440 (a large desktop, the chrome
a step up). Each further page/viewport combination exercises a distinct layout path or a denser
form not already covered. Other states run once where they bind, or are omitted when a kept case
covers the same elements and layout path in a harsher form. Its further viewports: the notch
phone, an iPhone 13 upright (the rotate panel, and the storybooks and the replay read upright),
1366x657 (a short desktop, the band's corners shared), 800x600 (a narrow desktop, a phone's chrome
on a desktop's geometry), 1280x720 and 1440x770 (laptop windows either side of the short
desktop's 760px, the latter the shortest regular desktop), 700x540 and 900x600 (small windows, a
panel against the board's width), 1024x510 (a short tablet, wide but under a phone's height) and
680x375 and 700x375 (wider phones at the floor's height). The composition is identical on all the
landscape ones. Upright, beside the iPhone 13 it adds 800x801, a near-square window with no touch
screen, whose densest right strip takes a second meld line beside the decisions and the notices.

## Review checklist

A review opens each anchor checkpoint at the three viewports and answers, in writing:

1. Can a player see the four zones and tell every tile's owner at a glance?
2. Is the player's next task the most prominent thing on screen, and the table still scannable?
3. Is each seat's identity in the place the reference fixed for it, the same in every checkpoint?
4. Do the rivers read as six-wide rows with space around each river and no two rivers touching?
5. Is there one strong cue for the seat in turn, is the latest discard found at a glance, and are
   the available actions ranked as above, with the two-step call's way back visible?
6. Are the decisions by the hand with the timer beside them, base and bank apart?
7. Does the surface between the core and the perimeter read as intentional space?
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
failures; neither is the accepted overflow of top and bottom third rows beyond nineteen discards), tap targets (40x40 for a button, a badge and a play switch, which
are controls; an own tile keeps the 32x42 floor on a phone, a safety limit; a desktop's own tile
follows the derived values and has no separate floor), readable faces and text sizes, text and marks
at a contrast of at least 4.5:1 against what they sit on (a held-back face included: it is greyed,
never darkened), no state told by colour alone (a switch's on state included; tile identity aside: a
red five is red and carries its own extra dot, which must stay visible at river scale), safe areas
respected, the rotate panel in a narrow portrait viewport, and, at the reference viewports, two
derived proportions held within a tolerance, the river tile over the own tile and each river's gap
from the centre, with neighbouring rivers no closer than that gap (a sparse river stands farther
from its neighbour); the opponent's hand at the river tile holds everywhere, and the other derived
values are review's, not the check's. Clarity, hierarchy and coherence are judged by the checklist
above. A visual failure that can be measured may earn a check; a judgement must not be turned into
an arbitrary pixel rule.
