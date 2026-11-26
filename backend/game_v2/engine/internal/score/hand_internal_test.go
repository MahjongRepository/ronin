package score

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
)

func winBlocksOf(t *testing.T, concealed string, m meld.Meld, winTile string) []hand.WinBlock {
	t.Helper()
	win := mustTile(t, winTile)
	counts, err := countHand(Hand{Concealed: mustTiles(t, concealed), WinTile: win, Melds: []meld.Meld{m}})
	if err != nil {
		t.Fatalf("countHand(%s + %s) error = %v", concealed, winTile, err)
	}

	readings := slices.Collect(counts.readings.All())
	if len(readings) != 1 {
		t.Fatalf("countHand(%s + %s) gives %d readings, want 1", concealed, winTile, len(readings))
	}

	return slices.Collect(readings[0].WinBlocks(win.Kind()))
}

func TestCountHand_ShouldCountRedFivesInConcealedTilesWinTileAndMelds(t *testing.T) {
	melds := []meld.Meld{
		newMeld(t, meld.Chi, "406s"),
		newMeld(t, meld.Pon, "111z"),
		newMeld(t, meld.Pon, "999m"),
	}

	counts, err := countHand(Hand{Concealed: mustTiles(t, "05m11p"), WinTile: mustTile(t, "0p"), Melds: melds})
	if err != nil {
		t.Fatalf("countHand error = %v", err)
	}

	if counts.akaDora != 3 {
		t.Errorf("countHand akaDora = %d, want 3", counts.akaDora)
	}
}

func TestCountHand_WhenTheWinningKindIsAlsoMelded_ShouldWinOnlyOnConcealedBlocks(t *testing.T) {
	oneToThreeMan := []hand.WinBlock{hand.SetWinBlock(hand.Set{Shape: hand.Sequence, Kind: 0})}
	for _, tc := range []struct {
		concealed string
		meld      meld.Meld
		winTile   string
		want      []hand.WinBlock
	}{
		{"13m456p789s55z", newMeld(t, meld.Chi, "123m"), "2m", oneToThreeMan},
		{"23m456p789s55z", newMeld(t, meld.Pon, "111m"), "1m", oneToThreeMan},
		{"234m456p789s5z", newMeld(t, meld.ClosedKan, "1111m"), "5z", []hand.WinBlock{hand.PairWinBlock()}},
	} {
		t.Run(tc.concealed+" + "+tc.winTile, func(t *testing.T) {
			if got := winBlocksOf(t, tc.concealed, tc.meld, tc.winTile); !slices.Equal(got, tc.want) {
				t.Errorf("win blocks of %s + %s with %v = %v, want %v", tc.concealed, tc.winTile, tc.meld, got, tc.want)
			}
		})
	}
}
