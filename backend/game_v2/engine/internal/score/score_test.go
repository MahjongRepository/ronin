package score_test

import (
	"fmt"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestWinIsTsumo_ShouldHoldForTsumoRinshanAndHaitei(t *testing.T) {
	for _, tc := range []struct {
		win  score.Win
		want bool
	}{
		{score.WinRon, false},
		{score.WinChankan, false},
		{score.WinHoutei, false},
		{score.WinTsumo, true},
		{score.WinRinshan, true},
		{score.WinHaitei, true},
	} {
		t.Run(fmt.Sprint(tc.win), func(t *testing.T) {
			if got := tc.win.IsTsumo(); got != tc.want {
				t.Errorf("Win(%d).IsTsumo() = %v, want %v", tc.win, got, tc.want)
			}
		})
	}
}

func TestSituationIsDealer_WhenTheSeatWindIsEast_ShouldHoldWhateverTheRoundWind(t *testing.T) {
	for _, tc := range []struct {
		seatWind, roundWind tile.Wind
		want                bool
	}{
		{tile.East, tile.East, true},
		{tile.South, tile.East, false},
		{tile.West, tile.East, false},
		{tile.North, tile.East, false},
		{tile.South, tile.South, false},
	} {
		t.Run(fmt.Sprintf("seat %v round %v", tc.seatWind, tc.roundWind), func(t *testing.T) {
			situation := score.Situation{Win: score.WinRon, SeatWind: tc.seatWind, RoundWind: tc.roundWind}
			if got := situation.IsDealer(); got != tc.want {
				t.Errorf("IsDealer() with seat %v, round %v = %v, want %v", tc.seatWind, tc.roundWind, got, tc.want)
			}
		})
	}
}
