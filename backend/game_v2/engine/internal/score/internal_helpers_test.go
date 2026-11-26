package score

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func mustTiles(t *testing.T, mpsz string) []tile.Tile {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	return parsed
}

func mustTile(t *testing.T, mpsz string) tile.Tile {
	t.Helper()
	parsed, err := tile.ParseTile(mpsz)
	if err != nil {
		t.Fatalf("ParseTile(%q) error = %v", mpsz, err)
	}

	return parsed
}

func kindOf(t *testing.T, mpsz string) tile.Kind {
	t.Helper()
	return mustTile(t, mpsz).Kind()
}

func countsOf(t *testing.T, mpsz string) [tile.KindCount]uint8 {
	t.Helper()
	counts, err := tile.CountsFromTiles(mustTiles(t, mpsz))
	if err != nil {
		t.Fatalf("CountsFromTiles(%q) error = %v", mpsz, err)
	}

	return counts.Array()
}

func kindsOf(t *testing.T, mpsz string) uint64 {
	t.Helper()
	var kinds uint64
	for _, parsed := range mustTiles(t, mpsz) {
		kinds |= uint64(1) << parsed.Kind()
	}

	return kinds
}

func newMeld(t *testing.T, kind meld.Kind, mpsz string) meld.Meld {
	t.Helper()
	parsed := mustTiles(t, mpsz)
	var m meld.Meld
	var err error
	switch kind {
	case meld.Chi:
		m, err = meld.NewChi([3]tile.Tile(parsed))
	case meld.Pon:
		m, err = meld.NewPon([3]tile.Tile(parsed))
	case meld.OpenKan:
		m, err = meld.NewOpenKan([4]tile.Tile(parsed))
	case meld.ClosedKan:
		m, err = meld.NewClosedKan([4]tile.Tile(parsed))
	}
	if err != nil {
		t.Fatalf("%v of %q error = %v", kind, mpsz, err)
	}

	return m
}

func decompositionOf(t *testing.T, mpsz string, index int) hand.Decomposition {
	t.Helper()
	counts, err := tile.CountsFromTiles(mustTiles(t, mpsz))
	if err != nil {
		t.Fatalf("CountsFromTiles(%q) error = %v", mpsz, err)
	}

	decompositions, err := hand.Divide(counts)
	if err != nil {
		t.Fatalf("Divide(%q) error = %v", mpsz, err)
	}

	all := slices.Collect(decompositions.All())
	if index >= len(all) {
		t.Fatalf("Divide(%q) gives %d readings, want reading %d", mpsz, len(all), index)
	}

	return all[index]
}

func readingOf(t *testing.T, mpsz string, melds ...meld.Meld) hand.Reading {
	t.Helper()
	return decompositionOf(t, mpsz, 0).Reading(hand.MeldSetsOf(melds))
}

func defaultRules() Rules {
	return Rules{
		DoubleYakuman: true, FuForOpenPinfu: true, FuForDoubleWindPair: 4, KazoeYakuman: true, RiichiStickValue: 1000, HonbaValue: 300,
	}
}
