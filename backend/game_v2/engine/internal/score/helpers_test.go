package score_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func tiles(tb testing.TB, mpsz string) []tile.Tile {
	tb.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		tb.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	return parsed
}

func oneTile(tb testing.TB, mpsz string) tile.Tile {
	tb.Helper()
	parsed, err := tile.ParseTile(mpsz)
	if err != nil {
		tb.Fatalf("ParseTile(%q) error = %v", mpsz, err)
	}

	return parsed
}

func chi(tb testing.TB, mpsz string) meld.Meld {
	tb.Helper()
	m, err := meld.NewChi([3]tile.Tile(threeTiles(tb, mpsz)))
	if err != nil {
		tb.Fatalf("NewChi(%q) error = %v", mpsz, err)
	}

	return m
}

func pon(tb testing.TB, mpsz string) meld.Meld {
	tb.Helper()
	m, err := meld.NewPon([3]tile.Tile(threeTiles(tb, mpsz)))
	if err != nil {
		tb.Fatalf("NewPon(%q) error = %v", mpsz, err)
	}

	return m
}

func openKan(tb testing.TB, mpsz string) meld.Meld {
	tb.Helper()
	m, err := meld.NewOpenKan([4]tile.Tile(fourTiles(tb, mpsz)))
	if err != nil {
		tb.Fatalf("NewOpenKan(%q) error = %v", mpsz, err)
	}

	return m
}

func closedKan(tb testing.TB, mpsz string) meld.Meld {
	tb.Helper()
	m, err := meld.NewClosedKan([4]tile.Tile(fourTiles(tb, mpsz)))
	if err != nil {
		tb.Fatalf("NewClosedKan(%q) error = %v", mpsz, err)
	}

	return m
}

func threeTiles(tb testing.TB, mpsz string) []tile.Tile {
	tb.Helper()
	parsed := tiles(tb, mpsz)
	if len(parsed) != 3 {
		tb.Fatalf("%q holds %d tiles, want 3", mpsz, len(parsed))
	}

	return parsed
}

func fourTiles(tb testing.TB, mpsz string) []tile.Tile {
	tb.Helper()
	parsed := tiles(tb, mpsz)
	if len(parsed) != 4 {
		tb.Fatalf("%q holds %d tiles, want 4", mpsz, len(parsed))
	}

	return parsed
}

func defaultRules() score.Rules {
	return score.Rules{DoubleYakuman: true, FuForOpenPinfu: true}
}

func ron() score.Situation {
	return score.Situation{Win: score.WinRon, SeatWind: tile.South, RoundWind: tile.East}
}

func tsumo() score.Situation {
	return score.Situation{Win: score.WinTsumo, SeatWind: tile.South, RoundWind: tile.East}
}

func withRiichi(situation score.Situation) score.Situation {
	situation.Riichi = play.Some(play.Riichi{})
	return situation
}

func concealedOf(tb testing.TB, wholeHand, winTile string, melds []meld.Meld) []tile.Tile {
	tb.Helper()
	concealed := tiles(tb, wholeHand)
	taken := []tile.Tile{oneTile(tb, winTile)}
	for _, m := range melds {
		taken = append(taken, m.Tiles()...)
	}

	for _, t := range taken {
		at := slices.Index(concealed, t)
		if at < 0 {
			tb.Fatalf("%q holds no %v of the melds and the winning tile", wholeHand, t)
		}

		concealed = slices.Delete(concealed, at, at+1)
	}

	return concealed
}

func valueOf(
	tb testing.TB,
	wholeHand, winTile string,
	melds []meld.Meld,
	situation score.Situation,
	dora score.Dora,
	rules score.Rules,
) (score.HandValue, error) {
	tb.Helper()
	h := score.Hand{
		Concealed: concealedOf(tb, wholeHand, winTile, melds),
		WinTile:   oneTile(tb, winTile),
		Melds:     melds,
	}
	return score.EstimateHandValue(h, situation, dora, rules)
}

func yakuIDs(value score.HandValue) []play.YakuID {
	ids := make([]play.YakuID, 0, len(value.Yaku))
	for _, y := range value.Yaku {
		ids = append(ids, y.ID)
	}

	return ids
}
