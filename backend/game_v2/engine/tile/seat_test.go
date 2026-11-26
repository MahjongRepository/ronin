package tile_test

import (
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestSeatWind_ShouldStartEastAtTheDealerAndFollowTurnOrder(t *testing.T) {
	seats := tile.Seats()
	for _, c := range []struct {
		dealer tile.Seat
		want   [4]tile.Wind
	}{
		{seats[2], [4]tile.Wind{tile.West, tile.North, tile.East, tile.South}},
		{seats[0], [4]tile.Wind{tile.East, tile.South, tile.West, tile.North}},
	} {
		t.Run("dealer "+strconv.Itoa(c.dealer.Index()), func(t *testing.T) {
			var got [4]tile.Wind
			for i, seat := range seats {
				got[i] = seat.Wind(c.dealer)
			}
			if got != c.want {
				t.Errorf("winds with dealer %d = %v, want %v", c.dealer.Index(), got, c.want)
			}
		})
	}
}

func TestSeatNextAndKamicha_ShouldWrapAroundTheTable(t *testing.T) {
	seats := tile.Seats()
	if got := seats[3].Next(); got != seats[0] {
		t.Errorf("seat 3 Next = %d, want 0", got.Index())
	}

	if got := seats[0].Kamicha(); got != seats[3] {
		t.Errorf("seat 0 Kamicha = %d, want 3", got.Index())
	}

	if got := seats[1].Next(); got != seats[2] {
		t.Errorf("seat 1 Next = %d, want 2", got.Index())
	}
}

func TestNewSeat_WhenNumberIsNotZeroToThree_ShouldRefuse(t *testing.T) {
	for _, n := range []int{-1, 4, 256} {
		if _, ok := tile.NewSeat(n); ok {
			t.Errorf("NewSeat(%d) accepted", n)
		}
	}

	if seat, ok := tile.NewSeat(3); !ok || seat.Index() != 3 {
		t.Errorf("NewSeat(3) = %d, %v; want seat 3", seat.Index(), ok)
	}
}
