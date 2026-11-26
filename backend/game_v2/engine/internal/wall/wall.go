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
	rinshanStacks   = deadWallStacks - indicatorStacks
	rinshanTiles    = 2 * rinshanStacks
	dealtTiles      = tile.SeatCount * StartingHandSize
)

const LiveWallSize = tile.TileIDCount - 2*deadWallStacks

const StartingHandSize = 13

const LiveTilesAtDeal = LiveWallSize - dealtTiles

// Stack is one stack of the dead wall: Top lies over Bottom. Top is a rinshan tile drawn first or a
// dora indicator, Bottom a rinshan tile drawn second or an ura dora indicator.
type Stack struct {
	Top, Bottom tile.TileID
}

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
