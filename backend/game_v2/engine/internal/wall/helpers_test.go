package wall_test

import (
	"slices"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
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

func stack(t *testing.T, top, bottom int) wall.Stack {
	t.Helper()
	return wall.Stack{Top: id(t, top), Bottom: id(t, bottom)}
}

func numbers(tiles []tile.TileID) []int {
	out := make([]int, 0, len(tiles))
	for _, tileID := range tiles {
		out = append(out, tileID.Index())
	}

	return out
}

func numberRange(from, to int) []int {
	out := make([]int, 0, to-from)
	for n := from; n < to; n++ {
		out = append(out, n)
	}

	return out
}

func seedOf(t *testing.T, pair string) rng.Seed {
	t.Helper()
	seed, err := rng.ParseSeed(strings.Repeat(pair, rng.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed(%q x 96) error = %v", pair, err)
	}

	return seed
}

func fixedSeed(t *testing.T) rng.Seed {
	t.Helper()
	return seedOf(t, "ab")
}

func orderedWall(t *testing.T) wall.Wall {
	t.Helper()
	w, err := wall.FromTiles(tile.AllTileIDs())
	if err != nil {
		t.Fatalf("FromTiles(every id once) error = %v", err)
	}

	return w
}

func sortedNumbers(tiles []tile.TileID) []int {
	sorted := slices.Clone(tiles)
	slices.SortFunc(sorted, tile.TileID.Compare)
	return numbers(sorted)
}

func dealtTiles(hands [tile.SeatCount][wall.StartingHandSize]tile.TileID) []tile.TileID {
	var dealt []tile.TileID
	for _, hand := range hands {
		dealt = append(dealt, hand[:]...)
	}

	return dealt
}

func mustDrawRinshan(t *testing.T, w *wall.Wall) tile.TileID {
	t.Helper()
	drawn, err := w.DrawRinshan()
	if err != nil {
		t.Fatalf("DrawRinshan error = %v", err)
	}

	return drawn
}

func mustAddDoraIndicator(t *testing.T, w *wall.Wall) tile.TileID {
	t.Helper()
	indicator, err := w.AddDoraIndicator()
	if err != nil {
		t.Fatalf("AddDoraIndicator error = %v", err)
	}

	return indicator
}

func mustIncrementPendingDora(t *testing.T, w *wall.Wall) {
	t.Helper()
	if err := w.IncrementPendingDora(); err != nil {
		t.Fatalf("IncrementPendingDora error = %v", err)
	}
}
