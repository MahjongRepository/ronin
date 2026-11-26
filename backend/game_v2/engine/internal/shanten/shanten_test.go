package shanten_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
)

func TestLowest_WhenHandIsKnown_ShouldCountItsLowestShape(t *testing.T) {
	tests := []struct {
		hand string
		want int
	}{
		{"123m456p789s11222z", shanten.Complete},
		{"123m456p789s1122z", 0},
		{"123456789m11p234s", shanten.Complete},
		{"123456789m13p24s", 1},
		{"123456m135p2468s", 2},
		{"13579m2468p159s1z", 4},
		{"12389m456p12789s1z", 1},
		{"1188m288p55s1177z", 0},
		{"1188m2288p55s1177z", shanten.Complete},
		{"1122m3344p556s11z", 0},
		{"112233m44556p77s", 0},
		{"19m19p19s1234567z", 0},
		{"119m19p19s1234567z", shanten.Complete},
		{"189m12p249s12345z", 4},
		{"1m", 0},
		{"2p3s", 0},
		{"11z", shanten.Complete},
		{"123m456p789s2z", 0},
		{"12m11p", 0},
		{"1111m", 1},
		{"1111m123p112233s", 1},
		{"11112222333444z", 1},
		{"1111444478m", 2},
		{"1111m2222p3333s1z", 2},
	}
	for _, tc := range tests {
		t.Run(tc.hand, func(t *testing.T) {
			got, err := shanten.Lowest(mustCounts(t, tc.hand))
			if err != nil || got != tc.want {
				t.Errorf("Lowest(%s) = %d, %v, want %d", tc.hand, got, err, tc.want)
			}
		})
	}
}

func TestLowest_WhenHandHasFewerThan13Tiles_ShouldLeaveOutKokushi(t *testing.T) {
	for _, hand := range []string{"19p19s1234567z", "19m19p19s1234z"} {
		t.Run(hand, func(t *testing.T) {
			counts := mustCounts(t, hand)
			got, err := shanten.Lowest(counts)
			if err != nil || got != 6 {
				t.Errorf("Lowest(%s) = %d, %v, want 6", hand, got, err)
			}
			if kokushi := shanten.Kokushi(counts); kokushi >= got {
				t.Errorf("Kokushi(%s) = %d, want below the lowest %d", hand, kokushi, got)
			}
		})
	}
}

func TestLowest_WhenNoHandHasTheTileCount_ShouldRefuseIt(t *testing.T) {
	tests := []struct {
		hand    string
		want    error
		message string
	}{
		{"", shanten.InvalidTileCountError{Count: 0}, "a hand of 0 tiles, a multiple of 3"},
		{"2p3s7z", shanten.InvalidTileCountError{Count: 3}, "a hand of 3 tiles, a multiple of 3"},
		{"123456789m", shanten.InvalidTileCountError{Count: 9}, "a hand of 9 tiles, a multiple of 3"},
		{"111222333444555m", shanten.TooManyTilesError{Count: 15}, "a hand of 15 tiles, more than 14"},
		{"123456789m1234567p", shanten.TooManyTilesError{Count: 16}, "a hand of 16 tiles, more than 14"},
	}
	for _, tc := range tests {
		t.Run(tc.hand, func(t *testing.T) {
			_, err := shanten.Lowest(mustCounts(t, tc.hand))
			if !errors.Is(err, tc.want) {
				t.Errorf("Lowest(%q) error = %v, want %v", tc.hand, err, tc.want)
				return
			}

			if err.Error() != tc.message {
				t.Errorf("Lowest(%q) error message = %q, want %q", tc.hand, err.Error(), tc.message)
			}
		})
	}
}

func TestChiitoitsu_WhenHandIsKnown_ShouldCountMissingPairsAndKinds(t *testing.T) {
	tests := []struct {
		hand string
		want int
	}{
		{"1122m3344p5566s11z", shanten.Complete},
		{"1188m2288p55s1177z", shanten.Complete},
		{"1122m3344p556s11z", 0},
		{"1188m288p55s1177z", 0},
		{"1122m3344p56s11z", 1},
		{"1188m2388p55s111z", 1},
		{"1188m288p55s1111z", 2},
		{"1188m288p555s111z", 2},
		{"1111m2222p3333s1z", 6},
		{"19m19p19s1234567z", 6},
		{"1z", 12},
	}
	for _, tc := range tests {
		t.Run(tc.hand, func(t *testing.T) {
			if got := shanten.Chiitoitsu(mustCounts(t, tc.hand)); got != tc.want {
				t.Errorf("Chiitoitsu(%s) = %d, want %d", tc.hand, got, tc.want)
			}
		})
	}
}

func TestKokushi_WhenHandIsKnown_ShouldCountMissingTerminalsAndHonors(t *testing.T) {
	tests := []struct {
		hand string
		want int
	}{
		{"19m19p19s12345677z", shanten.Complete},
		{"19m19p19s1234567z", 0},
		{"11m19p19s1234567z", 0},
		{"19m19p19s123456z", 1},
		{"119m12p299s12345z", 3},
		{"189m12p249s12345z", 4},
		{"234567m234567p2s", 13},
		{"23455m345p45678s", 13},
	}
	for _, tc := range tests {
		t.Run(tc.hand, func(t *testing.T) {
			if got := shanten.Kokushi(mustCounts(t, tc.hand)); got != tc.want {
				t.Errorf("Kokushi(%s) = %d, want %d", tc.hand, got, tc.want)
			}
		})
	}
}
