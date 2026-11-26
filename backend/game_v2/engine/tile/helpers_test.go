package tile_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func mustTile(t *testing.T, mpsz string) tile.Tile {
	t.Helper()
	parsed, err := tile.ParseTile(mpsz)
	if err != nil {
		t.Fatalf("ParseTile(%q) error = %v", mpsz, err)
	}

	return parsed
}

func mustTiles(t *testing.T, mpsz string) []tile.Tile {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	return parsed
}

func plainTiles(t *testing.T, kinds ...tile.Kind) []tile.Tile {
	t.Helper()
	tiles := make([]tile.Tile, 0, len(kinds))
	for _, kind := range kinds {
		plain, ok := tile.NewTile(kind)
		if !ok {
			t.Fatalf("NewTile(%d) refused", kind)
		}

		tiles = append(tiles, plain)
	}

	return tiles
}

func redFive(t *testing.T, kind tile.Kind) tile.Tile {
	t.Helper()
	red, ok := tile.RedFive(kind)
	if !ok {
		t.Fatalf("RedFive(%d) refused", kind)
	}

	return red
}

func mustID(t *testing.T, n int) tile.TileID {
	t.Helper()
	id, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
	}

	return id
}

func mustIDs(t *testing.T, ns ...int) []tile.TileID {
	t.Helper()
	ids := make([]tile.TileID, 0, len(ns))
	for _, n := range ns {
		ids = append(ids, mustID(t, n))
	}

	return ids
}

func kindNames() [tile.KindCount]string {
	return [tile.KindCount]string{
		"1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m",
		"1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p",
		"1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s", "9s",
		"1z", "2z", "3z", "4z", "5z", "6z", "7z",
	}
}
