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
  its shadow. This keeps the client light and fast on low-end phones.
- **Composed for ordinary play.** The design anchor is a mid-round state with real decisions on
  screen. Dense states (long rivers, four melds a seat, five dora indicators, long names) must
  stay legible and unambiguous but never reshape the ordinary composition.
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
  at whatever aspect ratio it has; nothing is letterboxed. An upright phone sees the rotate panel
  instead of play, which says that play and its timers go on. A replay or a storybook page may be
  read upright and scrolls instead.

## Composition (decisions)

```
+-------------------------------------------------------------------+
| dora, sticks  |                                      | menu, status|
|               |     top strip (backs)  [top badge]   |             |
| [left badge]  |                                      | [right badge]|
| left strip    |          [ top river ]               | right strip |
|               |  [L river]  [centre]  [R river]      |             |
|               |          [ bottom river ]            |             |
|  switches     |                   decisions   timer  |             |
|   [own badge] [ OWN HAND ...................... ] [melds]          |
|   furiten mark                                                     |
+-------------------------------------------------------------------+
```

The diagram is illustrative: it shows the three rings and the zones, not exact placements.

Four seat zones, top, left, right and bottom, are made perceptible on the surface. Decision: four
faint lines from the centre panel's corners, the upper two to the play area's top corners, the lower
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
  play area. Decision: a dark, subdued teal family, with the zone device and nothing else; ivory
  faces separate from it by value.
- **Centre.** One panel with an internal hierarchy: the round name large (East 1, South 4, a West
  round when the game runs on), the wall count with it; each seat's wind and score on the side
  facing it, all four at the same emphasis, tabular digits, the current dealer's wind marked; one
  primary cue on the centre for the seat in turn. Decision: each side's wind and score sit in one
  row, offset toward that seat's right like the rivers' pinwheel, so the four rows never meet at the
  corners; while a badge is pinned, the wall count stays and a label names whose differences show. A
  seat's accepted riichi stick lies on its side of the centre, as on a real table; this is where an
  established riichi is read, and the seat's badge only repeats it quietly. Decision: the stick lies
  along that side's edge of the centre panel, inside it, so the gap between the centre and the
  rivers stays free. The stick appears only once the declaration discard has passed without a ron,
  never when a ron or an abortive draw ends the hand on that discard; during the call window riichi
  is readable from the sideways tile and the callout alone. A seat's riichi marks reset at the next
  deal; sticks nobody collected stay in the pool. The turn cue lies on the panel's outer edge and
  the stick inside it, between the edge and the row, so a seat in turn and in riichi shows both
  apart.
- **Rivers.** Convention: each seat's river runs along its side, six tiles the normal row, three
  rows, reading left to right from the seat; a third row longer than six runs on along its own line;
  the riichi declaration discard lies sideways, and if that tile is claimed for a meld the
  declarer's next surviving discard lies sideways instead. Decision: the river starts at the
  centre's corner on the seat's left (the pinwheel). Decision: a claimed tile leaves the river, as
  on a real table; the current board keeps it greyed, and the change costs the river as a
  single-place chronology: a claimed tile stays identifiable in the meld that took it, with its
  feeder, so what that seat has passed can still be read, but a player reconstructs the seat's full
  discard order from river and melds together; the engine, not the player, judges furiten. A narrow
  but visible gap separates a river from the centre and from its neighbours; tiles touch inside a
  river, rivers never touch each other. Decision, departing from the run-on convention for side
  rivers only: at the 24-tile capacity a side river wraps its overflow into a fourth row of six
  toward its seat's edge, since a third row running on along a phone's short side would cross the
  hand; a top or bottom river keeps the convention, its third row running on along its line to
  twelve tiles. Every row reads left to right from its seat, so the river reads in order and as its
  owner's in every orientation. Decision: a drawn-and-discarded tile is not told apart from one
  played from the hand (Tenhou shades it, Mahjong Soul does not); the rivers keep as few tile states
  as possible so the latest discard and the riichi tile are found at a glance.
- **Latest discard.** Decision: the newest discard on the table is marked at all times, whether or
  not the viewer has an offer on it, so a player can always see what just happened, with a ring and
  a notch on its far side in a neutral colour, never the accent. The mark moves to each new discard
  and leaves with a tile that is claimed, since the claim is then read from the meld. During a
  discard offer this mark is the action source, and it outlives the offer, since a pass changes
  nothing on the table. A chankan offer's source is a kan in a meld and is marked separately, the
  whole kan ringed in its meld; while both are marked, the offered kan is what the controls refer
  to.
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
  revealed hand, a snapshot, a live draw the server announced); the seat's melds beyond the hand's
  right end at river scale. The strip is not a turn cue. Invariant: a strip stands apart from its own
  river, backs or faces, so that neither reads as a row of the other. Decision: a concealed hand,
  backs or faces, is 3:4 at the river tile's size (Tenhou's and Mahjong Soul's ratio), so an
  opponent's hand reads as plainly as its river. A side strip that cannot hold four melds on its
  line runs its oldest on a second line inside it, from the foreground band toward its badge; the
  top strip and the own melds scale down instead; no meld face goes under the 13x17 face floor.
  Decision: a side hand's full reach (fourteen tiles, the drawn one apart) has one fixed place per
  viewport, never read from the tiles held, and nothing else stands in it. The left hand runs down
  from below the counters, and the play switches step in past its depth where it would meet them.
  The right hand runs up from the band's top below the page's corner; where its full reach would
  then enter the band (a short desktop, the 667x375 floor), it runs up to the top margin instead and
  the corner steps in past its depth; where even that enters the band (the notch phone's shorter
  safe area), it runs from below the corner across the band, whose row then ends before it. A
  board without the page's corner (a replay's) keeps no room for it. The top
  hand stands centred, short of a badge's width before the page's corner and right of the counters.
- **Badges.** One fixed shape for every seat: wind, name, and marks for an AI player, a human seat
  an AI stands in for (the human identity kept, the mark cleared when they return), riichi (quiet)
  and disconnected. Each has a fixed place in its zone outside the rivers, the same in every state
  at a given viewport and viewpoint; a badge's place never depends on how many tiles the seat holds.
  A long name is shortened in the middle so its end, which tells AI players apart, stays. Decision:
  the badge carries no score; the centre holds every seat's score, and hovering or tapping a badge
  shows the other seats' scores in the centre as differences from it, labelled as that seat's
  differences (kept from the current board). The badge is therefore a control: its tap area meets
  the control floor whatever the drawn badge's size, a key activates it like a tap, a tap pins the
  differences, and tapping it again, tapping elsewhere or Escape returns the totals. An upright
  replay or storybook board may reduce the badge to the wind and marks. Decision: on a phone a side
  badge stands below the top river's capacity reach, so a long third row never meets it.
- **Pooled counters.** The five dora indicator slots (each indicator as a face once the event
  that reveals it has arrived, the rest unreadable backs; indicators are not the bonus tiles) with
  the honba and riichi-stick counts as icon and number, in one corner. Decision, not a
  convention: a real table keeps the honba counters by the dealer and the sticks by the centre,
  and the established clients differ; here they are shown once, with the dora, and the centre
  does not repeat them.
- **Own hand.** The play area's largest tiles, sorted, the drawn tile set apart by a gap at the
  right, the melds beyond it smaller; after a pon or chi there is no drawn tile and nothing is set
  apart. Every face stays readable in every state: a riichi hand is marked, never dimmed into
  darkness, and after riichi only the drawn tile looks discardable, while an offered tsumo or
  closed kan stays available. Tile states are told apart at a glance: selectable, selected, held
  back by a rule (kuikae after a call, a red and an ordinary five alike; a riichi discard that
  breaks tenpai: quiet, never hidden), and the tile an answer already played. Decision: a held-back
  tile shows reduced emphasis, never darkness: recessed (lower, slightly smaller, flat, without its
  edge and shadow) with a dashed inner rim, its ivory face and glyph colours unchanged, so every
  glyph keeps its contrast; while some tiles are held back the selectable ones stand slightly
  raised, and a selected or riichi-declaring tile is lifted and outlined in the accent.
- **Action source.** What an offer refers to is marked where it lies: the latest discard in its
  river, or for a chankan offer the whole kan in its meld (an added kan, or a closed kan robbed for
  kokushi musou). A discard's mark is the latest-discard mark and stays after the offer; a kan's
  mark goes when its chankan offer resolves. No callout, animation or automatic notice covers the
  action source or the faces that identify it while an offer is open; a sheet the player opens does,
  by the player's choice.
- **Decisions.** The decision controls have one stable place by the own hand, ranked: a win (ron,
  tsumo) outranks every other action; kyuushu kyuuhai, offered at a seat's first turn, ranks with a
  win since it ends the hand, with playing on as the alternative; calls, kan and riichi come next;
  pass is subordinate and never the most prominent thing on screen; several equally valid actions
  are presented as equals. Decision: a win is larger and ringed; on a phone it takes a row of its
  own above the calls. The controls show exactly the offer the server made and vanish when it
  resolves; an offer a play switch answers shows only as submitted, or not at all where the switch
  passes it (No calls). Decision: a call with a choice of tiles (which chi, which tile to kan) is
  taken in two steps, the call, then the tiles, with a way to go back, and an illegal combination is
  never selectable; the first step shows one control per kind, and at the second the choices are the
  controls, in the controls' place, each a tile group drawn as the meld will lie (the called tile
  turned toward its feeder, a closed kan's ends face down, an added kan's added tile stacked), with
  Back in the place of Pass. Riichi is a toggle that marks the discards that declare it on the hand
  and recesses the rest; it can be untoggled until the discard is sent, not after. A submitted
  answer and an expired decision each look different from an open one; expiry is the client's
  estimate, and the server's resulting move (a timeout's discard or pass) is shown when it arrives.
  After a reconnect the open decision resumes with its remaining time, never a fresh one, and no
  stale selection survives. Decision: on a desktop the controls and the timer after them stand in
  one row ending at the hand's right end, its drawn tile included; on a short desktop, whose core
  shares the band's corners, the row starts past the bottom river's capacity reach and the
  higher-ranked controls stand above the band's control and the timer (the band's control too where
  the row cannot hold it beside the timer), clear of the right strip as drawn. On a phone the lowest-ranked
  controls, pass last, take the foreground row beside the timer and never reach past the own river's
  capacity edge (a sideways riichi tile counted); the rest rise in rank order, right-aligned,
  between the right river's capacity edge and the right strip as drawn, pairing up before they would
  reach the side badge; at the first step a pair may shed its tile previews to fit, since the action
  source shows the tile, while the second step's groups always keep their tiles. Every control keeps
  visible space around its label and its choice tiles, the longest label at the floor viewport
  included; a target that meets the size floor with its text touching its border has failed.
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
  sent, bank), so expiry, submission and the bank never move it or the controls. It is the viewer's
  own: it shows for the viewer's open decision and round confirm only; the server sends no other
  seat's time, and none is drawn.
- **Turn cue.** One primary cue for the seat in turn, a neutral bar along its side of the centre,
  and one quiet reinforcement on its badge, neither in the accent; no further turn decoration: the
  current board's "Your turn" and "Your call" labels and the line under the hand are decoration and
  go. Selectable tiles, the latest discard and the decision controls keep their own states, which
  are information, not decoration.
- **Furiten.** A neutral status mark (a dot and the word) in a slot by the hand reserved so the
  hand never moves, not a button-shaped object and no prohibition sign, shown while the supplied
  state says the seat is furiten of any kind and cleared when it says so no longer; it gives no
  reason the state did not supply and never implies tsumo is unavailable.
- **Play switches.** Three toggles with one fixed place in the foreground, on the hand's side away
  from the decisions, clear of the left hand's full reach, answering for the player while on:
  *Auto win* takes a tsumo offer at once and a ron offer at once (decision: no pause, since the callout and the result show the claim and its
  feeder); *No calls* passes a call prompt that offers chi, pon or open kan and no ron, before its
  controls show, and never touches the viewer's own turn (closed kan, added kan, riichi, tsumo and
  kyuushu stay offered); *Auto discard* discards the drawn tile at once on a turn that offers
  nothing else, and leaves a turn with any other offer (tsumo, kan, riichi, kyuushu), and the turn
  after the viewer's own chi or pon, to the player. After riichi a draw is discarded by a press, or
  by *Auto discard* where it applies; the board adds no automatic post-riichi discard of its own. A
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
  automatic discard travels like a pressed one. Each switch shows on and off apart, not by colour
  alone (the established clients use grey against green), with a label a player understands without
  a manual, and meets the control floor; a switch is reached from the hand's focus like a decision
  control. Not on a replay board; the decisions stories show them, on and off. No auto-sort switch:
  the hand is always sorted. No forced auto-discard after idleness: the server's timeout and the AI
  stand-in cover an absent player.
- **Settings.** Not built: a settings sheet exists only while it has an entry, and it has none. The
  play switches are not settings: they last one hand and stay on the board.
- **Callouts.** Decision: a call, a riichi, a kan, a kyuushu kyuuhai declaration and a win show as
  one word on a chip over the caller's own river, upright, for a moment, large enough to read from
  across the board, a win's marked apart, covering no decision control, no face of the own hand and
  no action source; a double or triple ron shows every claimant's at once. Its life is the current
  board's: a fixed moment in live play or until a newer call at the same seat replaces it, and in a
  replay until the next stop. Candidate: a move may be animated briefly (a discard travels from hand
  to river); reduced motion turns it off.
- **Page corner.** The way back and the connection status, in one corner, small.
- **Notices.** Reconnecting, a lost seat, a refused move, a message the client could not read, tile
  faces that did not load: decision, their one place is the left zone's open field under the left
  badge, beside the left strip and outside every river's capacity, which a panel leaves free, so an
  automatic notice covers no tile, badge, control or panel; worded for a player, and a recoverable
  interruption looks different from an end. Several stack there, ongoing conditions first; in a
  replay the position and narration share the place, under any notice. A notice never loses its
  ending silently: one taller than its place shows whole lines and a "Show all" control, which opens
  the whole message in a sheet. The player chose it, so it covers the board as a panel does, the
  board inert beneath it, the focus in it and back on "Show all" when it closes, by Close or Escape;
  it says that play goes on, with the seconds left while a decision or the round confirm is open, as
  the rotate panel does. An ongoing condition (reconnecting, a seat lost, faces that did not load, a
  message the client could not read) stays until it recovers, is rebuilt or ends; an acknowledgement
  (the seat back, a refused move) leaves on its own after a moment. Nothing dismisses a failure that
  goes on. A connection replaced by another tab is an end, with its reason.
- **Panels.** Round results, standings, the seating before the first deal and the leave question use
  a legible overlay area over the board and dim it beneath; each has the size its content needs, not
  the core's; at the floor viewport a panel that does not fit scrolls inside its area with its
  primary button and countdown kept in view. The result, standings and seating leave the page corner
  reachable; the leave question is modal, says that an AI takes the seat over, makes staying the
  clear default, and need not. The seating shows the game's length and first round, every seat's
  wind and player, the dealer, AI players, the viewer, and the start countdown or that it waits.
  Candidate: each panel's placement over the board, drawn before it is built.
- **Round result.** Decision (the established clients order it differently; Tenhou's viewer puts
  the total first): the winner and how (ron, and from whom; tsumo; a head bump names who lost the
  ron); the winning hand with the winning tile set apart and its melds in their shape; the yaku,
  with han where han are meaningful and yakuman names and multipliers where they are; the dora,
  red and ura counts apart, the ura indicators only for a riichi winner and per winner in a double
  ron; the total (han and fu where meaningful, the limit name, the points) large; a note where a
  seat's payment is not the hand's value (pao, honba, collected sticks); every seat's change and
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
- **Standings.** Placement in the server's order, table points and adjusted results (uma and oka,
  the leftover riichi sticks) told apart, signed values kept, the ledger of every finished round
  with what its marks mean and each round reachable from it, the viewer's seat marked, and the
  ways on (the last result, this game's replay, the history, the lobby). A game that ended by
  tobi or at a round threshold is shown as completed, never as a failure. An ended session says
  why and offers the way back; it is not quiet.
- **Replay.** The board unchanged, its geometry identical to live play's, drawn from the chosen
  viewpoint seat, which need not be the reader's; plus controls with the position (round, step), the
  moves, play and speed, the viewpoint and hide-hands switches, the round list and the narration,
  readable at the floor viewport. Decision: the controls take the foreground band outside the own
  river's capacity reach, the moves in the switches' place and the options in the decisions' place,
  those that do not fit beside the reach on a phone in a row above before the right strip; the
  position and narration share the notices' place, under any notice. Loading, not found, incomplete
  and damaged replays each say so; an incomplete one shows no result for its unfinished round.
- **Material and type.** Ivory tile faces with room around the glyph, a small consistent edge and
  shadow; a red five reads as red at every scale, in a river, a meld, a revealed hand and a result;
  backs in one quiet colour. Decision: the face artwork (the committed SVG set) stays; the room
  around the glyph comes from the tile box, not from new drawings, and a glyph that is still
  unreadable at river scale with that room is reported, not redrawn in a ticket. Decision: one face,
  Inter, self-hosted as a Latin subset, with its tabular digits wherever numbers align; no
  monospace. Decision: one accent colour, used only for the player's own action (the primary
  control, the riichi toggle, a selected or declaring tile); the latest discard, the action source
  and the turn cue are neutral, and every text, mark and glyph on every face state keeps 4.5:1. Text
  keeps a readable size at every supported viewport; the gate's 10px floor is a safety limit, never
  the size to design to.

## Out of scope

Decided earlier and not reopened by this document: sound; languages other than English (the ja
and ru catalogs); player avatars, titles and other identity decoration beyond the badge; a
tenpai mark (the hand's waits and their remaining counts, live or in a replay); and hints that
judge the hand for the player: what each discard would wait on, which discard reaches tenpai,
shanten counts, safe tiles. The board gives no help beyond the state the server supplied.

## Proportions

Relationships first. The sizes come from one sizing rule; the derived column records the ratios it
gives at the three reference viewports and is not a range for other screens: 1280x800, 1920x1080 and
other phone heights follow the rule and are checked by the gate, not by this table.

The sizing rule. A landscape play area under 520 px high is a phone, anything taller a desktop; a
desktop under 760 px high and at least 1100 px wide (a laptop's browser window) is a short desktop.
The own hand tile is fixed at 36x48 on a phone and min(0.05 of the width, 0.1 of the height) wide on
a desktop. The river tile is the largest that keeps the centre's side at least 0.39 of the core on a
phone (0.33 on a desktop), starting from 0.65 of the own tile; the core's side is the centre plus
eight river tiles and two gaps of 0.3 of a river tile. On a desktop the core stands above the
foreground band, its side at most 0.66 of the height. On a phone and a short desktop the core fills
the height between the top strip's slot and the own hand, and the foreground band shares its lower
corners, which the pinwheel leaves empty, its controls kept outside every river's capacity reach.
An opponent's concealed hand tile is the river tile; its drawn tile stands 0.15 of a river tile
apart.

| Relationship | Starting point | Derived (667x375 / 750x369 notch safe area / 1440x900) |
|---|---|---|
| Core height / play area height | 0.6 | 0.74 / 0.74 / 0.63 |
| Centre side / core height | 0.3 | 0.41 / 0.40 / 0.34 |
| River tile width / own hand tile width | 0.65 | 0.53 / 0.53 / 0.61 |
| Opponent hand tile width / river tile width | 1.0 | 1.0 / 1.0 / 1.0 |
| Opponent hand tile width / own hand tile width | 0.65 | 0.53 / 0.53 / 0.61 |
| Own hand tile width / play area width | 0.05 | 0.054 / 0.048 / 0.050 |
| Own hand tile height / play area height | 0.15 | 0.13 / 0.13 / 0.11 |
| Gap between a river and the centre, in river tiles | 0.3 | 0.32 / 0.32 / 0.30 (0.3, rounded) |
| Gap between neighbouring rivers, in river tiles | 0.3 | 0.32 / 0.32 / 0.30 (0.3, rounded) |

A starting point is never a gate threshold. A derived value may become one, with a tolerance,
only where it protects the approved layout from a regression a player would notice.

The opponent's hand at the river tile follows Tenhou (every opponent hand and meld at exactly the
river tile, its own hand 1.44 of it on a desktop) and Mahjong Soul (the same, once its camera's depth
is taken out). A phone keeps its river tile, which the height binds; on a desktop the river grows
toward 0.65 of the own tile until the band or the core's cap binds: 1366x657 gives 0.47, 1920x1080
0.56. A decision control's tiles stay inside the room the band keeps for its row, so a large board's
controls never reach the bottom river.

The starting points did not fit together at the 667x375 floor. The rule resolves it by a mix: the
core grows to about three quarters of the height, since the foreground band shares the core's
lower corners where the pinwheel leaves them empty; the river tile shrinks; and the centre's share
grows rather than its text shrinking, so the round, the wall count and four winds with their
scores stay readable at the floor.

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
- **The rest**: the seating before the first deal, the round results, the standings, the leave
  question, a long notice opened in its sheet, the rotate panel during an open decision,
  the replay controls and its loading, incomplete and damaged states.

## Viewports

The reference is drawn, and every review opens, the same three: the 667x375 floor (iPhone SE), an
iPhone 13 in landscape with a notch's safe area (844x390 with insets of 47, 47 and 21), and
1440x900. The gate also runs 1280x800 and 1920x1080, and an iPhone 13 upright for the rotate panel.
The composition is identical on all the landscape ones.

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
failures; any other clipping is), tap targets (40x40 for a button, a badge and a play switch, which
are controls; an own tile keeps the 32x42 floor on a phone, a safety limit; a desktop's own tile
follows the derived values and has no separate floor), readable faces and text sizes, text and marks
at a contrast of at least 4.5:1 against what they sit on (a held-back face included: it is recessed,
never darkened), no state told by colour alone (a switch's on state included; tile identity aside: a
red five is red and carries its own extra dot, which must stay visible at river scale), safe areas
respected, the rotate panel on an upright phone, the budgets, and the derived proportions within
their tolerances once they exist. Clarity, hierarchy and coherence are judged by the checklist
above. A visual failure that can be measured may earn a check; a judgement must not be turned into
an arbitrary pixel rule.
