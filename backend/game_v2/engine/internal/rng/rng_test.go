package rng_test

import (
	"errors"
	"slices"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func repeatedSeed(t *testing.T, pair string) rng.Seed {
	t.Helper()
	seed, err := rng.ParseSeed(strings.Repeat(pair, rng.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed(%q x 96) error = %v", pair, err)
	}

	return seed
}

func seats(t *testing.T, ns ...int) [tile.SeatCount]tile.Seat {
	t.Helper()
	var out [tile.SeatCount]tile.Seat
	for i, n := range ns {
		seat, ok := tile.NewSeat(n)
		if !ok {
			t.Fatalf("NewSeat(%d) refused", n)
		}

		out[i] = seat
	}

	return out
}

func idNumbers(ids []tile.TileID) []int {
	numbers := make([]int, 0, len(ids))
	for _, id := range ids {
		numbers = append(numbers, id.Index())
	}

	return numbers
}

func TestParseSeed_WhenHexMixesCases_ShouldReadEveryDigitAndPrintItLowercase(t *testing.T) {
	hex := strings.Repeat("0123456789abcdefABCDEF01", 8)
	seed, err := rng.ParseSeed(hex)
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}

	wantFirst := [12]byte{0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef, 0xab, 0xcd, 0xef, 0x01}
	if got := [12]byte(seed[:12]); got != wantFirst {
		t.Errorf("first bytes = %x, want %x", got, wantFirst)
	}
	if got := seed.String(); got != strings.ToLower(hex) {
		t.Errorf("String() = %q, want %q", got, strings.ToLower(hex))
	}
}

func TestParseSeed_WhenStringIsMalformed_ShouldRefuseWithTheReason(t *testing.T) {
	cases := []struct {
		name string
		hex  string
		want error
	}{
		{"too short", strings.Repeat("ab", 10), rng.SeedLengthError{Length: 20}},
		{"first digit not hex", "zz" + strings.Repeat("ab", 95), rng.SeedNotHexError{}},
		{"second digit not hex", "az" + strings.Repeat("ab", 95), rng.SeedNotHexError{}},
		{"spaces", "  " + strings.Repeat("ab", 95), rng.SeedNotHexError{}},
		{"multibyte rune", "é" + strings.Repeat("ab", 95), rng.SeedNotHexError{}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if _, err := rng.ParseSeed(c.hex); !errors.Is(err, c.want) {
				t.Errorf("ParseSeed(%q) error = %v, want %v", c.hex, err, c.want)
			}
		})
	}
}

func TestRoundWall_WhenRoundIsZero_ShouldMatchThePinnedVector(t *testing.T) {
	wall, dice := rng.RoundWall(repeatedSeed(t, "ab"), 0)

	if got := idNumbers(wall[:8]); !slices.Equal(got, []int{113, 56, 116, 33, 121, 40, 115, 39}) {
		t.Errorf("first ids = %v", got)
	}
	if dice != (tile.Dice{First: 5, Second: 5}) {
		t.Errorf("dice = %v, want (5, 5)", dice)
	}

	sorted := wall
	slices.SortFunc(sorted[:], tile.TileID.Compare)
	if sorted != tile.AllTileIDs() {
		t.Errorf("wall is not a permutation of every id: %v", idNumbers(sorted[:]))
	}
}

func TestRoundWall_WhenRoundIsOne_ShouldMatchThePinnedVector(t *testing.T) {
	wall, dice := rng.RoundWall(repeatedSeed(t, "ab"), 1)

	want := []int{4, 52, 114, 92, 35, 49, 89, 53, 36, 113, 61, 7, 74, 66, 121, 117}
	if got := idNumbers(wall[:16]); !slices.Equal(got, want) {
		t.Errorf("first ids = %v, want %v", got, want)
	}
	if dice != (tile.Dice{First: 1, Second: 6}) {
		t.Errorf("dice = %v, want (1, 6)", dice)
	}
}

func TestRoundWall_WhenRoundsDiffer_ShouldShuffleDifferently(t *testing.T) {
	seed := repeatedSeed(t, "ab")
	round0, _ := rng.RoundWall(seed, 0)
	round1, _ := rng.RoundWall(seed, 1)
	if round0 == round1 {
		t.Error("rounds 0 and 1 have the same wall")
	}
}

func TestRoundWall_WhenRoundNeedsEveryByte_ShouldMatchThePinnedVector(t *testing.T) {
	wall, dice := rng.RoundWall(repeatedSeed(t, "ab"), 0x01020304)

	want := []int{68, 60, 99, 119, 8, 91, 95, 86}
	if got := idNumbers(wall[:8]); !slices.Equal(got, want) {
		t.Errorf("first ids = %v, want %v", got, want)
	}
	if dice != (tile.Dice{First: 5, Second: 2}) {
		t.Errorf("dice = %v, want (5, 2)", dice)
	}
}

func TestFirstDealer_ShouldMatchThePinnedVectors(t *testing.T) {
	cases := []struct {
		pair          string
		dealer        int
		first, second tile.Dice
	}{
		{"ab", 0, tile.Dice{First: 2, Second: 2}, tile.Dice{First: 5, Second: 1}},
		{"cd", 3, tile.Dice{First: 4, Second: 2}, tile.Dice{First: 1, Second: 6}},
	}
	for _, c := range cases {
		t.Run(c.pair, func(t *testing.T) {
			dealer, first, second := rng.FirstDealer(repeatedSeed(t, c.pair))
			if dealer.Index() != c.dealer || first != c.first || second != c.second {
				t.Errorf("FirstDealer(%s) = %d, %v, %v; want %d, %v, %v",
					c.pair, dealer.Index(), first, second, c.dealer, c.first, c.second)
			}
		})
	}
}

func TestFirstDealer_ShouldCountTheSecondThrowFromTheFirstThrowsSeat(t *testing.T) {
	dealer, first, second := rng.FirstDealer(repeatedSeed(t, "ab"))
	thrower := (first.Sum() - 1) % tile.SeatCount
	if want := (thrower + second.Sum() - 1) % tile.SeatCount; dealer.Index() != want {
		t.Errorf("dealer = %d, want %d", dealer.Index(), want)
	}
}

func TestSeatPermutation_ShouldMatchThePinnedVectors(t *testing.T) {
	cases := []struct {
		pair string
		want [tile.SeatCount]tile.Seat
	}{
		{"ab", seats(t, 2, 3, 0, 1)},
		{"cd", seats(t, 3, 2, 0, 1)},
	}
	for _, c := range cases {
		t.Run(c.pair, func(t *testing.T) {
			if got := rng.SeatPermutation(repeatedSeed(t, c.pair)); got != c.want {
				t.Errorf("SeatPermutation(%s) = %v, want %v", c.pair, got, c.want)
			}
		})
	}
}
