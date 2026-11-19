package score

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestIndicatorToDora_ShouldPointToTheNextTileOfItsGroup(t *testing.T) {
	for _, tc := range []struct{ indicator, dora string }{
		{"4m", "5m"}, {"1p", "2p"}, {"1s", "2s"}, {"9m", "1m"}, {"2z", "3z"}, {"4z", "1z"}, {"5z", "6z"}, {"7z", "5z"},
	} {
		if got := indicatorToDora(kindOf(t, tc.indicator)); got != kindOf(t, tc.dora) {
			t.Errorf("indicatorToDora(%s) = %d, want %s", tc.indicator, got, tc.dora)
		}
	}
}

func TestCountDoraForHand_WhenIndicatorsPointToHeldKinds_ShouldCountEachTileOncePerIndicator(t *testing.T) {
	for _, tc := range []struct {
		mpsz       string
		indicators []tile.Tile
		want       int
	}{
		{"123m456p789s11z", mustTiles(t, "5m"), 0},
		{"133m456p789s11z", mustTiles(t, "2m"), 2},
		{"133m456p789s11z", mustTiles(t, "22m"), 4},
		{"133m456p789s11z", slices.Concat(mustTiles(t, "2m"), mustTiles(t, "3p")), 3},
	} {
		if got := countDoraForHand(countsOf(t, tc.mpsz), tc.indicators); got != tc.want {
			t.Errorf("countDoraForHand(%s, %v) = %d, want %d", tc.mpsz, tc.indicators, got, tc.want)
		}
	}
}
