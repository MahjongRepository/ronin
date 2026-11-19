package shanten_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func mustCounts(t *testing.T, mpsz string) tile.Counts {
	t.Helper()
	tiles, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}
	counts, err := tile.CountsFromTiles(tiles)
	if err != nil {
		t.Fatalf("CountsFromTiles(%q) error = %v", mpsz, err)
	}
	return counts
}
