package tile_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestWindKindAndTile_ShouldBeTheWindsHonor(t *testing.T) {
	for _, c := range []struct {
		wind tile.Wind
		kind tile.Kind
		mpsz string
	}{
		{tile.East, 27, "1z"},
		{tile.South, 28, "2z"},
		{tile.West, 29, "3z"},
		{tile.North, 30, "4z"},
	} {
		if got := c.wind.Kind(); got != c.kind {
			t.Errorf("wind %d Kind = %d, want %d", c.wind, got, c.kind)
		}
		if got := c.wind.Tile(); got != mustTile(t, c.mpsz) {
			t.Errorf("wind %d Tile = %v, want %s", c.wind, got, c.mpsz)
		}
	}
}

func TestWindFromKind_ShouldInvertKindAndTakeOnlyTheWinds(t *testing.T) {
	for _, wind := range []tile.Wind{tile.East, tile.South, tile.West, tile.North} {
		if got, ok := tile.WindFromKind(wind.Kind()); !ok || got != wind {
			t.Errorf("WindFromKind(%d) = %d, %v; want %d", wind.Kind(), got, ok, wind)
		}
	}
	for _, kind := range []tile.Kind{26, 31, 255} {
		if _, ok := tile.WindFromKind(kind); ok {
			t.Errorf("WindFromKind(%d) accepted", kind)
		}
	}
}
