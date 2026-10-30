# Game client look

The visual specification of the v2 game client's board: what a player sees, how it is composed,
and how a change to it is judged. It describes the target in our own terms. The v2 client's
layout rules and its visual gate predate it and are reconciled with it once the drawn proposal
is approved; from then on, where they disagree, this document wins. `docs/game-rules.md` stays
the authority on what situations exist; this document only says how each is shown.

Status: draft. Three kinds of statement appear here, and a reader should know which is which:

- **Table conventions**: how riichi players read tiles on a table, verified against the World
  Riichi Championship and European Mahjong Association rules. These are not ours to change.
- **Composition decisions**: the board's structure and presentation choices, made deliberately
  after comparing the established online clients, which do not agree with each other on most of
  them. They bind the drawn proposal.
- **Candidates**: exact attachments, forms and counts, which the proposal confirms or moves. Where
  this document names a place or a form for an element, the invariant is that the element has one
  stable, predictable place within a viewport; the rest is a candidate unless marked a decision.

The proportions marked *derived* are filled in from the drawn proposal; until then they are
starting points, not requirements.

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

Four seat zones, top, left, right and bottom, are made perceptible on the surface (two faint
diagonals from the centre to the corners are the candidate device). They establish perceived
ownership; they are not clipping boundaries, and a long river may cross one. A seat's tiles and
the score data facing it are oriented toward that seat as on a real table: the top seat's tiles
upside down, a side seat's on their side, every river reading left to right from its own seat.
Names, notices, callouts and controls stay upright. The walls are not drawn; the wall count in
the centre and the indicator slots stand for them. The cost is the spatial picture: how much wall
is left and where the dead wall sits are read as a number, not seen, so emphasis on the count as
the wall runs out is a candidate.

- **Core**: the centre and the four rivers. Compact, centred, sized primarily by the play area's
  height and bounded by the width left beside the perimeter on a narrow landscape area. It does
  not grow with spare width.
- **Perimeter**: each opponent's strip and its badge, in its zone toward the play area's own
  edge. On a wide screen the side strips stand away from the core and the surface between them is
  intentional space, not a gap to fill.
- **Foreground**: the own hand, its badge and melds, the decisions and timer by it, the play
  switches and the furiten mark, over the bottom of the play area.

## Elements

- **Surface.** Fills the play area. One subdued colour family, the zone device, nothing else. The
  hue, and whether the surface is light or dark, are the proposal's to choose; the two treatments
  of the proposal may differ in exactly this.
- **Centre.** One panel with an internal hierarchy: the round name large (East 1, South 4, a West
  round when the game runs on), the wall count with it; each seat's wind and score on the side
  facing it, all four at the same emphasis, tabular digits, the current dealer's wind marked; one
  primary cue on the centre for the seat in turn. A seat's accepted riichi stick lies on its side
  of the centre, as on a real table; this is where an established riichi is read, and the seat's
  badge only repeats it quietly. Decision: the stick lies along that side's edge of the centre
  panel, inside it, so the gap between the centre and the rivers stays free. The stick appears
  only once the declaration discard has passed without a ron, never when a ron or an abortive
  draw ends the hand on that discard; during the
  call window riichi is readable from the sideways tile and the callout alone. A seat's riichi
  marks reset at the next deal; sticks nobody collected stay in the pool.
- **Rivers.** Convention: each seat's river runs along its side, six tiles the normal row, three
  rows, reading left to right from the seat; a third row longer than six runs on along its own
  line; the riichi declaration discard lies sideways, and if that tile is claimed for a meld the
  declarer's next surviving discard lies sideways instead. Decision: the river starts at the
  centre's corner on the seat's left (the pinwheel). Decision: a claimed tile leaves the river, as
  on a real table; the current board keeps it greyed, and the change costs the river as a
  single-place chronology: a claimed tile stays identifiable in the meld that took it, with its
  feeder, so what that seat has passed can still be read, but a player reconstructs the seat's
  full discard order from river and melds together; the engine, not the player, judges furiten. A
  narrow but visible gap
  separates a river from the centre and from its neighbours; tiles touch inside a river, rivers
  never touch each other. Whether a very long third row may wrap is decided on the drawn phone
  geometry; at 24 tiles, the layout capacity, the river must still read in chronological order and
  as its owner's, in every seat orientation. Candidate: whether a drawn-and-discarded tile is told
  apart quietly from one played from the hand (the protocol carries the flag on every discard;
  Tenhou shades it, Mahjong Soul does not) is the proposal's to draw or to decline in writing.
- **Latest discard.** Decision: the newest discard on the table is marked at all times, whether or
  not the viewer has an offer on it, so a player can always see what just happened. The mark moves
  to each new discard and leaves with a tile that is claimed, since the claim is then read from the
  meld. During a discard offer this mark is the action source, and it outlives the offer, since a
  pass changes nothing on the table. A chankan offer's source is a kan in a meld and is marked
  separately; while both are marked, the offered kan is what the controls refer to.
- **Melds**, every seat's. Convention: to the right of the hand from the seat's own view, the
  first meld farthest right and each later one toward the hand; the called tile sideways, at the
  meld's left when it came from the seat on the left, in the middle from the seat across, at the
  right from the seat on the right (a four-tile open kan from across has two middle positions:
  the proposal fixes one and it is used everywhere); a closed kan with its two end tiles face down
  (the form the rulebooks prefer; some tables turn the middle two); an added kan with the added
  tile sideways beside the called sideways tile, on its centre-facing side, both faces visible. A
  player reads who fed a meld from its shape alone, and tells a closed, open and added kan apart.
  Invariant: a visible gap separates the concealed hand from its melds and each meld from the next,
  at every seat and scale, so a closed kan never merges into the backs beside it; the proposal
  sets the gaps. A kan just declared, while a chankan may still rob it, reads as declared, not
  completed: no replacement draw and no new indicator show until the server sends them; a robbed
  kan stays readable as a robbed attempt in the result.
- **Opponent strips.** In the zone toward its edge, near the river tile's scale: tile backs in
  live play, the faces the mode reveals in a replay or a revealed result, in the same place
  either way; the drawn tile set apart only where the supplied state identifies one (a replay, a
  revealed hand, a snapshot); the seat's melds beyond the hand's right end at river scale. Live,
  other seats' draws are not announced to the client, so the strip never invents one and is not a
  turn cue. Invariant: a strip stands apart from its own river, backs or faces, so that neither
  reads as a row of the other; today the phone's top hand reads as an extra river row.
- **Badges.** One fixed shape for every seat: wind, name, and marks for an AI player, a human
  seat an AI stands in for (the human identity kept, the mark cleared when they return), riichi
  (quiet) and disconnected. Each has a fixed place in its zone outside the rivers, the same in
  every state at a given viewport and viewpoint; a badge's place never depends on how many tiles
  the seat holds. A long name is shortened in the middle so its end, which tells AI players apart,
  stays. Decision: the badge carries no score; the centre holds every seat's score, and hovering or
  tapping a badge shows the other seats' scores in the centre as differences from it, labelled as
  that seat's differences (kept from the current board). The badge is therefore a control: its tap
  area meets the control floor whatever the drawn badge's size, a key activates it like a tap, a tap
  pins the differences, and tapping it again, tapping elsewhere or Escape returns the totals. An
  upright replay or storybook board may reduce the badge to the wind and marks.
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
  breaks tenpai: quiet, never hidden), and the tile an answer already played.
- **Action source.** What an offer refers to is marked where it lies: the latest discard in its
  river, or for a chankan offer the whole kan in its meld (an added kan, or a closed kan robbed
  for kokushi musou). A discard's mark is the latest-discard mark and stays after the offer; a
  kan's mark goes when its chankan offer resolves. No callout, animation or notice covers the
  action source or the faces that identify it while an offer is open.
- **Decisions.** The decision controls have one stable place by the own hand, ranked: a win
  (ron, tsumo) outranks every other action; kyuushu kyuuhai, offered at a seat's first turn, ranks
  with a win since it ends the hand, with playing on as the alternative; calls, kan and riichi
  come next; pass is subordinate and never the most prominent thing on screen; several equally
  valid actions are presented as equals. The controls show exactly the offer the server made and
  vanish when it resolves; an offer a play switch answers shows only as submitted, or not at all
  where the switch passes it (No calls). Decision: a call with a choice of tiles (which chi, which tile to kan)
  is taken in two steps, the call, then the tiles, with a way to go back, and an illegal
  combination is never selectable; whether the second step is chosen on the hand itself or as
  small groups beside the controls is the proposal's to draw. Riichi is a toggle that marks the
  discards that declare it on the hand and dims the rest; it can be untoggled until the discard
  is sent, not after. A submitted answer and an expired decision each look different from an open
  one; expiry is the client's estimate, and the server's resulting move (a timeout's discard or
  pass) is shown when it arrives. After a reconnect the open decision resumes with its remaining
  time, never a fresh one, and no stale selection survives. How many rows the controls use on the
  smallest phone is the proposal's to draw. Every control keeps visible space around its label and
  its choice tiles, the longest label at the floor viewport included; a target that meets the size
  floor with its text touching its border has failed.
- **Input.** The contract the current board has, kept unless the proposal draws and justifies a
  change: a tile of the own hand is a button; one tap, click, Enter or Space on a selectable tile
  sends it, with no separate confirm step, and a tile that is not selectable takes the press and
  does nothing. A decision control sends on one press, except the riichi toggle and the first step
  of a two-step call, which only change what the next press means and are undone by pressing them
  again, by the way back or by Escape. A play switch is a board control, not a decision control:
  pressing it changes what the client answers from then on and sends nothing itself. Focus stays
  in the hand through a turn, and an offer's
  controls are reached from it without the focus being moved for the player. An expired decision
  still takes one answer, since the server alone decides by the wait whether it counts; an answer
  the server refuses while the wait goes on reopens the decision as answerable, with the refusal
  as a notice. The proposal draws a touch confirm step (select, then confirm) beside the one-press
  hand at the floor viewport as a comparison for the user to choose from; the drawing does not
  make two-tap play the default, whose extra gesture costs time on every turn.
- **Timer.** The countdown beside the decision controls as large digits, the base time and the
  bank apart (`5 +20`), the bank marked while it alone is draining, so a player always knows
  which time is being spent. It is the viewer's own: it shows for the viewer's open decision and
  round confirm only; the server sends no other seat's time, and none is drawn.
- **Turn cue.** One primary cue for the seat in turn, on the centre, and one quiet reinforcement
  on its badge; no further turn decoration: the current board's "Your turn" and "Your call" labels
  and the line under the hand are decoration and go. Selectable tiles, the latest discard and the
  decision controls keep their own states, which are information, not decoration.
- **Furiten.** A status mark by the hand, not a button-shaped object, shown while the supplied
  state says the seat is furiten of any kind and cleared when it says so no longer; it gives no
  reason the state did not supply and never implies tsumo is unavailable.
- **Play switches.** Three toggles with one fixed place in the foreground, on the hand's side
  away from the decisions, answering for the player while on: *Auto win* takes a tsumo offer at
  once and a ron offer at once (candidate: after a short fixed moment, so the discard that fed it
  is seen first); *No calls* passes a call prompt that offers chi, pon or open kan and no ron,
  before its controls show, and never touches the viewer's own turn (closed kan, added kan, riichi,
  tsumo and kyuushu stay offered); *Auto discard* discards the drawn tile at once on a turn that
  offers nothing else, and leaves a turn with any other offer (tsumo, kan, riichi, kyuushu), and
  the turn after the viewer's own chi or pon, to the player. A win always outranks a discard or a
  pass, so with both switches on a tsumo offer wins. A switch answers a wait the first time the
  client sees its id while the switch is on, and never a wait it has already seen: not the
  decision already open when the switch is turned on, so nothing moves under the player's finger;
  not the same wait re-sent after a reconnect, which resumes the decision as it was, answered or
  not; and not a decision the server's refusal reopened, which is the player's to answer again.
  Decision: all three reset at each deal, and when a reconnect's snapshot shows another hand or a
  round result pending, since a switch is an instruction about this hand (Tenhou's manual clears
  its no-call every hand and its auto-discard when the mouse was touched; the all-three reset is
  this board's own choice). Candidate: *Auto win* kept across deals. They survive a reconnect
  within the hand in the mounted client; a reload or a new tab starts with them off. They are the
  client's standing answers, taken exactly where the player's press would be, with the decision's
  wait id, so the server, which keeps no preference, sees an ordinary answer; the latest-discard
  mark and the table are unchanged by an automatic pass, and an automatic discard travels like a
  pressed one. Each switch shows on and off apart, not by colour alone (the established clients
  use grey against green), with a label a player understands without a manual, and meets the
  control floor; a switch is reached from the hand's focus like a decision control. Not on a
  replay board; the decisions stories show them, on and off. No auto-sort switch: the hand is
  always sorted. No forced auto-discard after idleness: the server's timeout and the AI stand-in
  cover an absent player.
- **Settings.** A sheet opened from the page corner, over the board like the other panels, that
  holds the preferences that outlive a hand: the touch confirm step (Input) where the user keeps
  it as a choice rather than a default, and, when they arrive, sound and language; the
  replay's own preferences (speed, hidden hands) stay the replay's. It exists only while it has
  an entry: a sheet with nothing to hold is not built, and the drawing and checklist duties here
  go with it. Play and its timers go on beneath it, so it says so with the seconds left (a
  decision's, or the round confirm's) as the rotate panel does; the board beneath is inert as
  under any panel, the focus enters the sheet and returns to the corner's control when it closes,
  and Escape closes the sheet alone. It stays open when a decision opens within the hand, so it
  never closes under the player's finger, and closes on its own close, on the next deal, and when
  a reconnect's snapshot shows another hand; an end, the leave question and a round result take
  precedence over it, and it may be opened over a result, showing the confirm's countdown.
  Preferences are the viewer's, kept in this browser (the replay's preference store is the
  pattern: defaults when storage is blocked), never on the server. The play switches are not
  settings: they last one hand and stay on the board.
- **Callouts.** Candidate form: a call, a riichi, a kan, a kyuushu kyuuhai declaration and a win
  show as one word by the seat that made it, for a moment, large enough to read from across the
  board, covering no decision control, no face of the own hand and no action source; a double or
  triple ron shows every claimant's at once. Its life is the current board's: a fixed moment in
  live play or until a newer call at the same seat replaces it, and in a replay until the next
  stop. A move may be animated briefly (a discard travels from hand to river); reduced motion
  turns it off.
- **Page corner.** The way back and the connection status, in one corner, small.
- **Notices.** Reconnecting, a lost seat, a refused move, a message the client could not read,
  tile faces that did not load: each has one fixed place that covers no tile, badge, control or
  panel, worded for a player, and a recoverable interruption looks different from an end. An
  ongoing condition (reconnecting, a seat lost, faces that did not load, a message the client
  could not read) stays until it recovers, is rebuilt or ends; an acknowledgement (the seat back,
  a refused move) leaves on its own after a moment. Nothing dismisses a failure that goes on. A
  connection replaced by another tab is an end, with its reason.
- **Panels.** Round results, standings, the seating before the first deal and the leave question
  use a legible overlay area over the board and dim it beneath; each has the size its content
  needs, not the core's; at the floor viewport a panel that does not fit scrolls inside its area
  with its primary button and countdown kept in view. The result, standings and seating leave the
  page corner reachable; the
  leave question is modal, says that an AI takes the seat over, makes staying the clear default,
  and need not. The seating shows the game's length and first round, every seat's wind and
  player, the dealer, AI players, the viewer, and the start countdown or that it waits.
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
- **Replay.** The board unchanged, drawn from the chosen viewpoint seat, which need not be the
  reader's; plus controls (as a bar or a column, the proposal's choice at each viewport) with the
  position (round, step), the moves, play and speed, the viewpoint and hide-hands switches, the
  round list and the narration, readable at the floor viewport. Loading, not found, incomplete
  and damaged replays each say so; an incomplete one shows no result for its unfinished round.
- **Material and type.** Ivory tile faces with room around the glyph, a small consistent edge and
  shadow; a red five reads as red at every scale, in a river, a meld, a revealed hand and a
  result; backs in one quiet colour. Decision: the face artwork (the committed SVG set) stays; the
  room around the glyph comes from the tile box, not from new drawings, and a glyph that is still
  unreadable at river scale with that room is reported, not redrawn in a ticket. One sans-serif
  face; tabular digits wherever numbers align; no monospace. Text keeps a readable size at every
  supported viewport; the gate's 10px floor is a safety limit, never the size to design to.

## Out of scope

Decided earlier and not reopened by this document: sound; languages other than English (the ja
and ru catalogs); player avatars, titles and other identity decoration beyond the badge; a
tenpai mark (the hand's waits and their remaining counts, live or in a replay); and hints that
judge the hand for the player: what each discard would wait on, which discard reaches tenpai,
shanten counts, safe tiles. The board gives no help beyond the state the server supplied.

## Proportions

Relationships first; the numbers are derived from the drawn proposal so they hold together at
every supported viewport. A derived value may be a range or qualified by viewport, since a
width-bound hand, a height-bound core and a fixed tile shape cannot all keep one ratio across
aspect ratios. The derived column is filled in when the proposal is approved.

| Relationship | Starting point | Derived |
|---|---|---|
| Core height / play area height | 0.6 | |
| Centre side / core height | 0.3 | |
| River tile width / own hand tile width | 0.6 | |
| Opponent back width / river tile width | 0.75 | |
| Own hand tile width / play area width | 0.05 | |
| Own hand tile height / play area height | 0.15 | |
| Gap between a river and the centre, in river tiles | 0.3 | |
| Gap between neighbouring rivers, in river tiles | 0.3 | |

A starting point is never a gate threshold. A derived value may become one, with a tolerance,
only where it protects the approved layout from a regression a player would notice.

The starting points do not fit together at the 667x375 floor: six river rows and a centre at 0.3
of the core already exceed a core at 0.6 of the height. That is expected of starting points; the
proposal resolves it, by a taller core, a smaller river tile, a smaller centre or a mix, and
records the result in the derived column. The centre's starting side is about 0.18 of the play
area's height at the floor, where it holds the round, the wall count, four winds and four scores;
the review reads that text at the floor, and the derived values may move the centre's share
rather than shrink its text.

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
  question, the settings sheet over an open decision, the rotate panel during an open decision,
  the replay controls and its loading, incomplete and damaged states.

## Viewports

The proposal is drawn, and every review opens, the same three: the 667x375 floor (iPhone SE), an
iPhone 13 in landscape with a notch's safe area, and 1440x900. The gate also runs 1280x800 and
1920x1080, and an iPhone 13 upright for the rotate panel. The composition is identical on all
the landscape ones.

## Review checklist

A review opens each anchor checkpoint at the three viewports and answers, in writing:

1. Can a player see the four zones and tell every tile's owner at a glance?
2. Is the player's next task the most prominent thing on screen, and the table still scannable?
3. Is each seat's identity in the place the proposal fixed for it, the same in every checkpoint?
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

The automated visual checks protect the measurable floor: no required information or control
hidden, clipped or overflowing (concealed faces and content that legitimately scrolls or sits
behind a modal are not failures), tap targets (40x40 for a button, a badge and a play switch,
which are controls; an own tile keeps the retained 32x42 floor on a phone, a safety limit the
proposal exceeds where it can), readable faces and text sizes, text and marks at a contrast of at
least 4.5:1 against what they sit on (a dimmed tile face included: it is quiet, never unreadable),
no state told by colour alone (a switch's on state included; tile identity aside: a red five is
red and carries its own extra dot, which must stay visible at river scale), safe areas respected, the rotate panel on an upright
phone, the budgets, and the derived proportions within their tolerances once they exist. Clarity,
hierarchy and coherence are judged by the checklist above. A visual failure that can be measured
may earn a check; a judgement must not be turned into an arbitrary pixel rule.
