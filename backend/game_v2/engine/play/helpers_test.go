package play_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func id(t *testing.T, n int) tile.TileID {
	t.Helper()
	got, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
	}

	return got
}

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}

	return got
}

func copies(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	var seen [tile.KindCount]int
	ids := make([]tile.TileID, 0, len(parsed))
	for _, parsedTile := range parsed {
		kind := parsedTile.Kind()
		ids = append(ids, id(t, int(kind)*tile.CopiesPerKind+first+seen[kind]))
		seen[kind]++
	}

	return ids
}

func copyOf(t *testing.T, first int, mpsz string) tile.TileID {
	t.Helper()
	ids := copies(t, first, mpsz)
	if len(ids) != 1 {
		t.Fatalf("%q holds %d tiles, want 1", mpsz, len(ids))
	}

	return ids[0]
}
