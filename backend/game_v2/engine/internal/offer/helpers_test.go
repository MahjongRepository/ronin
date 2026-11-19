package offer_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
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
		offset := first + seen[kind]
		if offset >= tile.CopiesPerKind {
			t.Fatalf("%q repeats a kind past its copies", mpsz)
		}
		ids = append(ids, id(t, int(kind)*tile.CopiesPerKind+offset))
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

func kindOf(t *testing.T, mpsz string) tile.Kind {
	t.Helper()
	return copyOf(t, 0, mpsz).Kind()
}

func calledMeld(t *testing.T, kind play.MeldKind, first int, mpsz string, from tile.Seat) play.MeldView {
	t.Helper()
	tiles := copies(t, first, mpsz)
	return offer.NewMeldView(kind, tiles[0], tiles[1:], from)
}

func closedKan(t *testing.T, mpsz string) play.MeldView {
	t.Helper()
	return play.MeldView{Kind: play.MeldClosedKan, Tiles: copies(t, 0, mpsz)}
}

func river(tiles []tile.TileID) []play.RiverTile {
	discards := make([]play.RiverTile, len(tiles))
	for i, discarded := range tiles {
		discards[i] = play.RiverTile{Tile: discarded}
	}
	return discards
}

func concat(parts ...[]tile.TileID) []tile.TileID {
	return slices.Concat(parts...)
}
