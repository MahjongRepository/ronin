package hand_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func mustTiles(tb testing.TB, mpsz string) []tile.Tile {
	tb.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		tb.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	return parsed
}

func mustCounts(tb testing.TB, mpsz string) tile.Counts {
	tb.Helper()
	counts, err := tile.CountsFromTiles(mustTiles(tb, mpsz))
	if err != nil {
		tb.Fatalf("CountsFromTiles(%q) error = %v", mpsz, err)
	}

	return counts
}

func mustCountsFromArray(t *testing.T, counts [tile.KindCount]uint8) tile.Counts {
	t.Helper()
	valid, err := tile.CountsFromArray(counts)
	if err != nil {
		t.Fatalf("CountsFromArray(%v) error = %v", counts, err)
	}

	return valid
}

func mustKind(t *testing.T, mpsz string) tile.Kind {
	t.Helper()
	parsed, err := tile.ParseTile(mpsz)
	if err != nil {
		t.Fatalf("ParseTile(%q) error = %v", mpsz, err)
	}

	return parsed.Kind()
}

func kindsString(t *testing.T, kinds tile.Kinds) string {
	t.Helper()
	return kindListString(t, slices.Collect(kinds.All()))
}

func kindListString(t *testing.T, kinds []tile.Kind) string {
	t.Helper()
	tiles := make([]tile.Tile, 0, len(kinds))
	for _, kind := range kinds {
		plain, ok := tile.NewTile(kind)
		if !ok {
			t.Fatalf("NewTile(%d) refused", kind)
		}

		tiles = append(tiles, plain)
	}

	return tile.TilesString(tiles)
}

func mustDivide(t *testing.T, mpsz string) []hand.Decomposition {
	t.Helper()
	decompositions, err := hand.Divide(mustCounts(t, mpsz))
	if err != nil {
		t.Fatalf("Divide(%s) error = %v", mpsz, err)
	}

	return slices.Collect(decompositions.All())
}

func setsMpsz(t *testing.T, d hand.Decomposition) []string {
	t.Helper()
	var sets []string
	for _, set := range d.KindSets() {
		sets = append(sets, kindListString(t, set))
	}

	return sets
}

func mustPon(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewPon([3]tile.Tile(mustTiles(t, mpsz)))
	if err != nil {
		t.Fatalf("NewPon(%s) error = %v", mpsz, err)
	}

	return m
}

func mustOpenKan(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewOpenKan([4]tile.Tile(mustTiles(t, mpsz)))
	if err != nil {
		t.Fatalf("NewOpenKan(%s) error = %v", mpsz, err)
	}

	return m
}

func mustClosedKan(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewClosedKan([4]tile.Tile(mustTiles(t, mpsz)))
	if err != nil {
		t.Fatalf("NewClosedKan(%s) error = %v", mpsz, err)
	}

	return m
}

func mustChi(t *testing.T, mpsz string) meld.Meld {
	t.Helper()
	m, err := meld.NewChi([3]tile.Tile(mustTiles(t, mpsz)))
	if err != nil {
		t.Fatalf("NewChi(%s) error = %v", mpsz, err)
	}

	return m
}

func reading(t *testing.T, mpsz string, melds []meld.Meld, index int) hand.Reading {
	t.Helper()
	decompositions := mustDivide(t, mpsz)
	if index >= len(decompositions) {
		t.Fatalf("Divide(%s) gave %d readings, want reading %d", mpsz, len(decompositions), index)
	}

	return decompositions[index].Reading(hand.MeldSetsOf(melds))
}
