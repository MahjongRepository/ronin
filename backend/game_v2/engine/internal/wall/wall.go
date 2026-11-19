// Package wall holds the wall of a round by role: the live wall in draw order, and the dead
// wall's rinshan tiles, dora indicator stacks and reserve.
//
// The 136 tiles lie in a ring of 68 two-tile stacks, 17 in front of each seat. The dice pick the
// break; the seven stacks from the break are the dead wall, two rinshan stacks then five
// indicator stacks, each showing a dora indicator on top with its ura dora indicator beneath. The
// live wall starts at the stack before the break and runs away from it. A rinshan draw moves the
// last live tile into the reserve, so the dead wall always holds 14 tiles.
//
// Ported from the wall module of mahjong-rs's mahjong-game.
package wall

import (
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	stacksPerSeat   = 17
	totalStacks     = tile.TileIDCount / 2
	deadWallStacks  = 7
	indicatorStacks = 5
	rinshanTiles    = 4
	dealtTiles      = tile.SeatCount * StartingHandSize
)

// LiveWallSize is the live wall before the deal: the 136 tiles less the dead wall's 14.
const LiveWallSize = tile.TileIDCount - 2*deadWallStacks

// StartingHandSize is the number of tiles the deal gives each seat.
const StartingHandSize = 13

// LiveTilesAtDeal is the live wall once the hands are dealt: 122 tiles less the 52 dealt.
const LiveTilesAtDeal = LiveWallSize - dealtTiles

// Stack is one stack of the dead wall: Top lies over Bottom. Top is a rinshan tile drawn first or a
// dora indicator, Bottom a rinshan tile drawn second or an ura dora indicator.
type Stack struct {
	Top, Bottom tile.TileID
}

// Wall is the wall of one round, a value: copying it copies every tile. Every tile it owns is in
// exactly one role. The live wall is held whole in its draw order: the deal and the draws take
// from its front, and a rinshan draw moves its back tile into the reserve, so the reserve is the
// live wall's tail in reverse and holds one tile per rinshan tile drawn.
type Wall struct {
	live       [LiveWallSize]tile.TileID
	drawn      int
	reserved   int
	rinshan    [rinshanTiles]tile.TileID
	indicators [indicatorStacks]Stack
	revealed   int
	pending    int
	dice       tile.Dice
}

// DuplicateTileError reports an explicit wall that lists Tile more than once.
type DuplicateTileError struct {
	Tile tile.TileID
}

func (e DuplicateTileError) Error() string {
	return "the wall lists tile " + strconv.Itoa(e.Tile.Index()) + " twice"
}

// RinshanExhaustedError reports a rinshan draw after all four rinshan tiles are drawn.
type RinshanExhaustedError struct{}

func (RinshanExhaustedError) Error() string {
	return "no rinshan tile is left"
}

// LiveWallEmptyError reports a rinshan draw with no live tile left to move into the reserve.
type LiveWallEmptyError struct{}

func (LiveWallEmptyError) Error() string {
	return "the live wall is empty"
}

// IndicatorsExhaustedError reports a dora reveal or deferral when every indicator is revealed or
// pending.
type IndicatorsExhaustedError struct{}

func (IndicatorsExhaustedError) Error() string {
	return "every dora indicator is revealed or pending"
}

// BreakStack returns the stack, 0 to 67, where the dead wall starts: counting the dice sum from
// the dealer picks a seat, and the break is that many stacks from the right end of its 17.
func BreakStack(dice tile.Dice, dealer tile.Seat) int {
	diceSum := dice.Sum()
	target := (dealer.Index() + diceSum - 1) % tile.SeatCount
	return ((target+1)*stacksPerSeat - diceSum) % totalStacks
}

// FromSeed returns the wall of round roundNumber of the game with seed, broken for dealer.
func FromSeed(seed rng.Seed, roundNumber uint32, dealer tile.Seat) Wall {
	shuffled, dice := rng.RoundWall(seed, roundNumber)
	return FromShuffle(shuffled, dice, dealer)
}

// FromShuffle breaks a shuffled ring at the stack dice and dealer pick. Stack k of the ring holds
// shuffled[2k] on top of shuffled[2k+1].
func FromShuffle(shuffled [tile.TileIDCount]tile.TileID, dice tile.Dice, dealer tile.Seat) Wall {
	start := BreakStack(dice, dealer)
	stack := func(k int) Stack {
		return Stack{Top: shuffled[2*k], Bottom: shuffled[2*k+1]}
	}

	var dead [deadWallStacks]Stack
	for i := range dead {
		dead[i] = stack((start + i) % totalStacks)
	}

	var live [LiveWallSize]tile.TileID
	for i := range totalStacks - deadWallStacks {
		s := stack((start + totalStacks - 1 - i) % totalStacks)
		live[2*i], live[2*i+1] = s.Top, s.Bottom
	}
	return fromParts(live, dead, dice)
}

// FromTiles returns a wall in an explicit order, as ronin's tests and replays give it: the first
// 122 tiles are the live wall in draw order, the last 14 the dead wall's stacks from the break,
// the 7 tops then the 7 bottoms. The dice are (1, 1). A DuplicateTileError names the first tile
// listed twice.
func FromTiles(tiles [tile.TileIDCount]tile.TileID) (Wall, error) {
	var seen [tile.TileIDCount]bool
	for _, id := range tiles {
		if seen[id.Index()] {
			return Wall{}, DuplicateTileError{Tile: id}
		}
		seen[id.Index()] = true
	}

	var dead [deadWallStacks]Stack
	for i := range dead {
		dead[i] = Stack{Top: tiles[LiveWallSize+i], Bottom: tiles[LiveWallSize+deadWallStacks+i]}
	}
	live := [LiveWallSize]tile.TileID(tiles[:LiveWallSize])
	return fromParts(live, dead, tile.Dice{First: 1, Second: 1}), nil
}

func fromParts(live [LiveWallSize]tile.TileID, dead [deadWallStacks]Stack, dice tile.Dice) Wall {
	return Wall{
		live:       live,
		rinshan:    [rinshanTiles]tile.TileID{dead[0].Top, dead[0].Bottom, dead[1].Top, dead[1].Bottom},
		indicators: [indicatorStacks]Stack(dead[2:]),
		revealed:   1,
		dice:       dice,
	}
}

// Deal deals the starting hands from the front of the live wall: three blocks of four tiles to
// each seat from dealer, then one each. The hands are by seat, each sorted by id. A round deals
// once, on a wall fresh from its constructor: Deal always deals the first 52 tiles the live wall
// was built with and leaves the draws to start after them.
func (w *Wall) Deal(dealer tile.Seat) [tile.SeatCount][StartingHandSize]tile.TileID {
	var hands [tile.SeatCount][StartingHandSize]tile.TileID
	var held [tile.SeatCount]int
	next := 0
	for _, size := range [...]int{4, 4, 4, 1} {
		seat := dealer
		for range tile.SeatCount {
			i := seat.Index()
			copy(hands[i][held[i]:], w.live[next:next+size])
			held[i] += size
			next += size
			seat = seat.Next()
		}
	}

	for i := range hands {
		slices.SortFunc(hands[i][:], tile.TileID.Compare)
	}
	w.drawn = dealtTiles
	return hands
}

// Draw draws the next live tile; false once the live wall is empty.
func (w *Wall) Draw() (tile.TileID, bool) {
	if w.LiveCount() == 0 {
		return tile.TileID{}, false
	}
	w.drawn++
	return w.live[w.drawn-1], true
}

// DrawRinshan draws the next rinshan tile and moves the last live tile into the reserve. A
// RinshanExhaustedError after four rinshan draws, and a LiveWallEmptyError when no live tile is
// left to move.
func (w *Wall) DrawRinshan() (tile.TileID, error) {
	if w.reserved == rinshanTiles {
		return tile.TileID{}, RinshanExhaustedError{}
	}
	if w.LiveCount() == 0 {
		return tile.TileID{}, LiveWallEmptyError{}
	}
	w.reserved++
	return w.rinshan[w.reserved-1], nil
}

// AddDoraIndicator reveals the next dora indicator and returns it. An IndicatorsExhaustedError
// when the revealed and pending indicators already make five.
func (w *Wall) AddDoraIndicator() (tile.TileID, error) {
	if w.revealed+w.pending >= indicatorStacks {
		return tile.TileID{}, IndicatorsExhaustedError{}
	}
	w.revealed++
	return w.indicators[w.revealed-1].Top, nil
}

// IncrementPendingDora defers one kan dora reveal until the kan caller's discard settles or a
// further kan stands. An IndicatorsExhaustedError when the revealed and pending indicators already
// make five.
func (w *Wall) IncrementPendingDora() error {
	if w.revealed+w.pending >= indicatorStacks {
		return IndicatorsExhaustedError{}
	}
	w.pending++
	return nil
}

// RevealPendingDora reveals every deferred kan dora and returns them in reveal order.
func (w *Wall) RevealPendingDora() []tile.TileID {
	first := w.revealed
	w.revealed += w.pending
	w.pending = 0
	return tops(w.indicators[first:w.revealed])
}

// ClearPendingDora drops the deferred kan dora reveals without revealing them, as a tsumo on the
// rinshan tile scores before they show.
func (w *Wall) ClearPendingDora() {
	w.pending = 0
}

// Live returns a copy of the live tiles in draw order.
func (w Wall) Live() []tile.TileID {
	return slices.Clone(w.live[w.drawn : LiveWallSize-w.reserved])
}

// LiveCount returns how many live tiles are left.
func (w Wall) LiveCount() int {
	return LiveWallSize - w.reserved - w.drawn
}

// Rinshan returns a copy of the rinshan tiles left, in draw order.
func (w Wall) Rinshan() []tile.TileID {
	return slices.Clone(w.rinshan[w.reserved:])
}

// Indicators returns the five indicator stacks, in reveal order.
func (w Wall) Indicators() [indicatorStacks]Stack {
	return w.indicators
}

// Reserve returns the live tiles that rinshan draws moved into the dead wall, in the order they
// moved.
func (w Wall) Reserve() []tile.TileID {
	reserve := make([]tile.TileID, 0, w.reserved)
	for i := range w.reserved {
		reserve = append(reserve, w.live[LiveWallSize-1-i])
	}
	return reserve
}

// RevealedCount returns how many dora indicators are revealed, 1 to 5.
func (w Wall) RevealedCount() int {
	return w.revealed
}

// PendingDoraCount returns how many kan dora reveals are deferred.
func (w Wall) PendingDoraCount() int {
	return w.pending
}

// Dice returns the dice of the wall break.
func (w Wall) Dice() tile.Dice {
	return w.dice
}

// DoraIndicators returns the revealed dora indicators, in reveal order.
func (w Wall) DoraIndicators() []tile.TileID {
	return tops(w.indicators[:w.revealed])
}

// UraIndicators returns the ura dora indicators a riichi winner counts: the one under each
// revealed indicator, as kan ura dora (has_kan_uradora) is on.
func (w Wall) UraIndicators() []tile.TileID {
	ura := make([]tile.TileID, 0, w.revealed)
	for _, s := range w.indicators[:w.revealed] {
		ura = append(ura, s.Bottom)
	}
	return ura
}

// Tiles returns every tile the wall owns: live, rinshan, the indicator stacks top then bottom,
// and the reserve.
func (w Wall) Tiles() []tile.TileID {
	owned := w.Live()
	owned = append(owned, w.Rinshan()...)
	for _, s := range w.indicators {
		owned = append(owned, s.Top, s.Bottom)
	}
	return append(owned, w.Reserve()...)
}

func tops(stacks []Stack) []tile.TileID {
	ids := make([]tile.TileID, 0, len(stacks))
	for _, s := range stacks {
		ids = append(ids, s.Top)
	}
	return ids
}
