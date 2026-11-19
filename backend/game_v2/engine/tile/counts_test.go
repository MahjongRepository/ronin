package tile_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestCountsFromTiles_ShouldCountARedFiveAsItsKind(t *testing.T) {
	counts, err := tile.CountsFromTiles(mustTiles(t, "1105m1p"))
	if err != nil {
		t.Fatalf("CountsFromTiles error = %v", err)
	}
	for mpsz, want := range map[string]int{"1m": 2, "5m": 2, "0m": 2, "1p": 1, "2m": 0} {
		if got := counts.Count(mustTile(t, mpsz)); got != want {
			t.Errorf("Count(%s) = %d, want %d", mpsz, got, want)
		}
	}
}

func TestCountsFromArray_WhenAKindHasFiveTiles_ShouldNameTheLowest(t *testing.T) {
	var tiles34 [tile.KindCount]uint8
	tiles34[27], tiles34[30] = 5, 9
	_, err := tile.CountsFromArray(tiles34)
	if !errors.Is(err, tile.TooManyCopiesError{Kind: 27}) {
		t.Fatalf("CountsFromArray error = %v, want kind 27 too many", err)
	}
	if got, want := err.Error(), "kind 27 has more than 4 tiles"; got != want {
		t.Errorf("error message = %q, want %q", got, want)
	}
}

func TestCountsFromArray_WhenEveryKindHasAtMostFour_ShouldKeepTheCounts(t *testing.T) {
	var tiles34 [tile.KindCount]uint8
	tiles34[0], tiles34[33] = 4, 3
	counts, err := tile.CountsFromArray(tiles34)
	if err != nil || counts.Array() != tiles34 {
		t.Errorf("CountsFromArray = %v, %v; want %v", counts.Array(), err, tiles34)
	}
}
