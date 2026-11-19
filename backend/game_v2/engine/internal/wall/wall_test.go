package wall_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func stackIndex(seatIndex, positionFromRight int) int {
	return seatIndex*17 + 17 - positionFromRight
}

func physicalLayout(dealer int, dice tile.Dice) (live, dead []int) {
	diceSum := dice.Sum()
	var walk []int
	wallSeat, position := (dealer+diceSum-1)%4, diceSum+1
	for len(walk) < 68 {
		if position > 17 {
			wallSeat, position = (wallSeat+3)%4, 1
		}
		walk = append(walk, stackIndex(wallSeat, position))
		position++
	}

	dead = slices.Clone(walk[61:])
	slices.Reverse(dead)
	return walk[:61], dead
}

func stackOf(t *testing.T, index int) wall.Stack {
	t.Helper()
	return stack(t, 2*index, 2*index+1)
}

func TestFromShuffle_WhenAnyDealerThrowsAnyDice_ShouldMatchThePhysicalCount(t *testing.T) {
	for _, dealer := range tile.Seats() {
		for first := 1; first <= 6; first++ {
			for second := 1; second <= 6; second++ {
				dice := tile.Dice{First: first, Second: second}
				w := wall.FromShuffle(tile.AllTileIDs(), dice, dealer)
				live, dead := physicalLayout(dealer.Index(), dice)

				var wantLive []int
				for _, index := range live {
					wantLive = append(wantLive, 2*index, 2*index+1)
				}
				if got := numbers(w.Live()); !slices.Equal(got, wantLive) {
					t.Errorf("dealer %d, dice %v: live = %v, want %v", dealer.Index(), dice, got, wantLive)
				}

				wantRinshan := []int{2 * dead[0], 2*dead[0] + 1, 2 * dead[1], 2*dead[1] + 1}
				if got := numbers(w.Rinshan()); !slices.Equal(got, wantRinshan) {
					t.Errorf("dealer %d, dice %v: rinshan = %v, want %v", dealer.Index(), dice, got, wantRinshan)
				}

				var wantIndicators [5]wall.Stack
				for i := range wantIndicators {
					wantIndicators[i] = stackOf(t, dead[2+i])
				}
				if got := w.Indicators(); got != wantIndicators {
					t.Errorf("dealer %d, dice %v: indicators = %v, want %v", dealer.Index(), dice, got, wantIndicators)
				}
			}
		}
	}
}

func TestFromShuffle_WhenDealerZeroThrowsFive_ShouldBreakTheDealersOwnWall(t *testing.T) {
	w := wall.FromShuffle(tile.AllTileIDs(), tile.Dice{First: 2, Second: 3}, seat(t, 0))
	if got, want := w.Rinshan()[0].Index(), 2*stackIndex(0, 5); got != want {
		t.Errorf("first rinshan = %d, want %d", got, want)
	}
	if got, want := w.Indicators()[4].Top.Index(), 2*stackIndex(1, 16); got != want {
		t.Errorf("last indicator top = %d, want %d", got, want)
	}
}

func TestFromSeed_ShouldPartitionAllTilesWithOneDoraRevealed(t *testing.T) {
	w := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))

	if w.LiveCount() != 122 || len(w.Live()) != 122 {
		t.Errorf("live = %d (%d listed), want 122", w.LiveCount(), len(w.Live()))
	}
	if got := len(w.Tiles()) - w.LiveCount(); got != 14 {
		t.Errorf("dead wall holds %d tiles, want 14", got)
	}
	if got := sortedNumbers(w.Tiles()); !slices.Equal(got, numberRange(0, 136)) {
		t.Errorf("tiles = %v, want every id once", got)
	}
	if got := w.DoraIndicators(); !slices.Equal(got, []tile.TileID{w.Indicators()[0].Top}) {
		t.Errorf("dora indicators = %v, want the first stack's top", numbers(got))
	}
	if len(w.Rinshan()) != 4 || len(w.Reserve()) != 0 {
		t.Errorf("rinshan = %v, reserve = %v; want 4 rinshan, no reserve", w.Rinshan(), w.Reserve())
	}
}

func TestFromSeed_WhenInputsAreTheSame_ShouldBuildTheSameWall(t *testing.T) {
	first := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))
	second := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))
	if first != second {
		t.Error("two walls of the same seed, round and dealer differ")
	}
}

func TestFromSeed_WhenSeedOrRoundDiffers_ShouldBuildAnotherLiveWall(t *testing.T) {
	base := numbers(wall.FromSeed(fixedSeed(t), 0, seat(t, 0)).Live())
	if slices.Equal(base, numbers(wall.FromSeed(seedOf(t, "cd"), 0, seat(t, 0)).Live())) {
		t.Error("another seed gives the same live wall")
	}
	if slices.Equal(base, numbers(wall.FromSeed(fixedSeed(t), 1, seat(t, 0)).Live())) {
		t.Error("another round gives the same live wall")
	}
}

func TestFromSeed_WhenDealerDiffers_ShouldKeepTheDiceAndBreakElsewhere(t *testing.T) {
	wall0 := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))
	wall1 := wall.FromSeed(fixedSeed(t), 0, seat(t, 1))
	if wall0.Dice() != wall1.Dice() {
		t.Errorf("dice = %v and %v, want the same", wall0.Dice(), wall1.Dice())
	}
	if slices.Equal(numbers(wall0.Live()), numbers(wall1.Live())) {
		t.Error("both dealers break at the same stack")
	}
}

func TestFromSeed_WhenSeedIsTheFixedSeed_ShouldMatchThePinnedLayout(t *testing.T) {
	w := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))

	if got := wall.BreakStack(w.Dice(), seat(t, 0)); got != 24 {
		t.Errorf("break stack = %d, want 24", got)
	}
	if got := numbers(w.Live()[:8]); !slices.Equal(got, []int{0, 73, 43, 55, 19, 51, 95, 112}) {
		t.Errorf("first live = %v", got)
	}
	if got := numbers(w.Rinshan()); !slices.Equal(got, []int{30, 41, 45, 131}) {
		t.Errorf("rinshan = %v", got)
	}
	wantIndicators := [5]wall.Stack{
		stack(t, 52, 99), stack(t, 97, 127), stack(t, 18, 53), stack(t, 120, 135), stack(t, 82, 91),
	}
	if got := w.Indicators(); got != wantIndicators {
		t.Errorf("indicators = %v, want %v", got, wantIndicators)
	}

	hands := w.Deal(seat(t, 0))
	wantHands := [4][]int{
		{0, 6, 26, 35, 43, 54, 55, 62, 67, 73, 79, 88, 100},
		{4, 19, 23, 49, 51, 95, 101, 106, 112, 122, 124, 130, 134},
		{20, 21, 39, 40, 58, 60, 63, 69, 98, 115, 121, 132, 133},
		{5, 9, 13, 29, 33, 56, 61, 90, 92, 93, 111, 113, 116},
	}
	for i, hand := range hands {
		if got := numbers(hand[:]); !slices.Equal(got, wantHands[i]) {
			t.Errorf("hand %d = %v, want %v", i, got, wantHands[i])
		}
	}
	if drawn, ok := w.Draw(); !ok || drawn.Index() != 72 {
		t.Errorf("first draw = %d, %v; want 72", drawn.Index(), ok)
	}
}

func TestFromTiles_ShouldLayOutLiveThenDeadStacks(t *testing.T) {
	w := orderedWall(t)

	if got := numbers(w.Live()); !slices.Equal(got, numberRange(0, 122)) {
		t.Errorf("live = %v, want 0..121", got)
	}
	if got := numbers(w.Rinshan()); !slices.Equal(got, []int{122, 129, 123, 130}) {
		t.Errorf("rinshan = %v", got)
	}
	var wantIndicators [5]wall.Stack
	for i := range wantIndicators {
		wantIndicators[i] = stack(t, 124+i, 131+i)
	}
	if got := w.Indicators(); got != wantIndicators {
		t.Errorf("indicators = %v, want %v", got, wantIndicators)
	}
	if got := numbers(w.DoraIndicators()); !slices.Equal(got, []int{124}) {
		t.Errorf("dora indicators = %v, want [124]", got)
	}
	if w.Dice() != (tile.Dice{First: 1, Second: 1}) {
		t.Errorf("dice = %v, want (1, 1)", w.Dice())
	}
}

func TestFromTiles_WhenATileIsListedTwice_ShouldRefuseNamingIt(t *testing.T) {
	tiles := tile.AllTileIDs()
	tiles[5] = id(t, 3)
	if _, err := wall.FromTiles(tiles); !errors.Is(err, wall.DuplicateTileError{Tile: id(t, 3)}) {
		t.Errorf("FromTiles error = %v, want tile 3 listed twice", err)
	}
}

func TestDeal_ShouldGiveEachSeat13SortedDistinctTiles(t *testing.T) {
	w := orderedWall(t)
	hands := w.Deal(seat(t, 0))

	for i, hand := range hands {
		if !slices.IsSortedFunc(hand[:], tile.TileID.Compare) {
			t.Errorf("hand %d = %v is not sorted", i, numbers(hand[:]))
		}
	}
	if got := slices.Compact(sortedNumbers(dealtTiles(hands))); len(got) != 52 {
		t.Errorf("%d distinct tiles dealt, want 52", len(got))
	}
	if w.LiveCount() != wall.LiveTilesAtDeal {
		t.Errorf("live = %d, want %d", w.LiveCount(), wall.LiveTilesAtDeal)
	}
}

func TestDeal_ShouldGiveTheDealerTheFirstBlock(t *testing.T) {
	for _, dealer := range []tile.Seat{seat(t, 0), seat(t, 2)} {
		w := orderedWall(t)
		hands := w.Deal(dealer)
		if got := numbers(hands[dealer.Index()][:4]); !slices.Equal(got, []int{0, 1, 2, 3}) {
			t.Errorf("dealer %d first block = %v, want 0..3", dealer.Index(), got)
		}
		if got := numbers(hands[dealer.Next().Index()][:4]); !slices.Equal(got, []int{4, 5, 6, 7}) {
			t.Errorf("dealer %d shimocha first block = %v, want 4..7", dealer.Index(), got)
		}
	}
}

func TestDeal_WhenAnyDealerDeals_ShouldLeaveTheLiveTilesAtDeal(t *testing.T) {
	for _, dealer := range tile.Seats() {
		w := wall.FromSeed(fixedSeed(t), 0, dealer)
		w.Deal(dealer)
		if w.LiveCount() != wall.LiveTilesAtDeal {
			t.Errorf("dealer %d: live = %d, want %d", dealer.Index(), w.LiveCount(), wall.LiveTilesAtDeal)
		}
	}
}

func TestDraw_ShouldTakeTheFrontOfTheLiveWallUntilItIsEmpty(t *testing.T) {
	w := orderedWall(t)
	for want := range 122 {
		if drawn, ok := w.Draw(); !ok || drawn.Index() != want {
			t.Fatalf("draw %d = %d, %v", want, drawn.Index(), ok)
		}
	}

	if drawn, ok := w.Draw(); ok {
		t.Errorf("draw from an empty wall = %d", drawn.Index())
	}
	if w.LiveCount() != 0 || len(w.Live()) != 0 {
		t.Errorf("live = %d, want 0", w.LiveCount())
	}
}

func TestDrawRinshan_ShouldTakeTheTwoBreakSideStacksTopFirst(t *testing.T) {
	w := orderedWall(t)
	var drawn []tile.TileID
	for range 4 {
		drawn = append(drawn, mustDrawRinshan(t, &w))
	}
	if got := numbers(drawn); !slices.Equal(got, []int{122, 129, 123, 130}) {
		t.Errorf("rinshan draws = %v", got)
	}
	if len(w.Rinshan()) != 0 {
		t.Errorf("rinshan left = %v, want none", numbers(w.Rinshan()))
	}
}

func TestDrawRinshan_ShouldMoveTheLastLiveTileIntoTheReserve(t *testing.T) {
	w := orderedWall(t)
	mustDrawRinshan(t, &w)

	if got := numbers(w.Reserve()); !slices.Equal(got, []int{121}) {
		t.Errorf("reserve = %v, want [121]", got)
	}
	if got := numbers(w.Live()); !slices.Equal(got, numberRange(0, 121)) {
		t.Errorf("live = %v, want 0..120", got)
	}
	if got := len(w.Tiles()) - w.LiveCount(); got != 14 {
		t.Errorf("dead wall holds %d tiles, want 14", got)
	}
}

func TestDrawRinshan_WhenTheLiveWallIsEmpty_ShouldRefuse(t *testing.T) {
	w := orderedWall(t)
	for {
		if _, ok := w.Draw(); !ok {
			break
		}
	}

	if _, err := w.DrawRinshan(); !errors.Is(err, wall.LiveWallEmptyError{}) {
		t.Errorf("DrawRinshan error = %v, want the live wall empty", err)
	}
}

func TestDrawRinshan_WhenFourAreDrawn_ShouldRefuse(t *testing.T) {
	w := orderedWall(t)
	for range 4 {
		mustDrawRinshan(t, &w)
	}

	if _, err := w.DrawRinshan(); !errors.Is(err, wall.RinshanExhaustedError{}) {
		t.Errorf("DrawRinshan error = %v, want rinshan exhausted", err)
	}
}

func TestWallErrors_ShouldNameWhatIsWrong(t *testing.T) {
	cases := []struct {
		err  error
		want string
	}{
		{wall.DuplicateTileError{Tile: id(t, 3)}, "the wall lists tile 3 twice"},
		{wall.RinshanExhaustedError{}, "no rinshan tile is left"},
		{wall.LiveWallEmptyError{}, "the live wall is empty"},
		{wall.IndicatorsExhaustedError{}, "every dora indicator is revealed or pending"},
		{wall.MissingTileError{Tile: id(t, 7)}, "tile 7 is nowhere"},
		{wall.TileInTwoPlacesError{Tile: id(t, 100)}, "tile 100 is in more than one place"},
	}
	for _, c := range cases {
		if got := c.err.Error(); got != c.want {
			t.Errorf("%#v message = %q, want %q", c.err, got, c.want)
		}
	}
}
