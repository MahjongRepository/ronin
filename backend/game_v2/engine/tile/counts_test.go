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

func TestCountsWithoutOne_WhenTheKindIsHeld_ShouldTakeOneTileOut(t *testing.T) {
	counts, err := tile.CountsFromTiles(mustTiles(t, "112m"))
	if err != nil {
		t.Fatalf("CountsFromTiles error = %v", err)
	}

	rest, ok := counts.WithoutOne(0)
	if !ok || rest.Count(mustTile(t, "1m")) != 1 || rest.Count(mustTile(t, "2m")) != 1 {
		t.Errorf("WithoutOne(1m) = %v, %v; want one 1m and one 2m left", rest.Array(), ok)
	}

	if counts.Count(mustTile(t, "1m")) != 2 {
		t.Errorf("WithoutOne changed its receiver to %v", counts.Array())
	}
}

func TestCountsWithoutOne_WhenTheKindIsNotHeldOrPastTheLast_ShouldRefuse(t *testing.T) {
	counts, err := tile.CountsFromTiles(mustTiles(t, "1m"))
	if err != nil {
		t.Fatalf("CountsFromTiles error = %v", err)
	}

	for _, kind := range []tile.Kind{1, tile.KindCount, 255} {
		if rest, ok := counts.WithoutOne(kind); ok || rest != counts {
			t.Errorf("WithoutOne(%d) = %v, %v; want the counts unchanged, false", kind, rest.Array(), ok)
		}
	}
}
