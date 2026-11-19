package score_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestHandRules_ShouldBeTenhousPresetBuiltFromTheRuleConstants(t *testing.T) {
	tenhou := score.Rules{OpenTanyao: true, FuForOpenPinfu: true}

	if got := score.HandRules(); got != tenhou {
		t.Errorf("HandRules() = %+v, want %+v", got, tenhou)
	}
}

func TestRuleConstants_ShouldMatchTheScoringHelpers(t *testing.T) {
	for _, tc := range []struct {
		name     string
		constant int
		helper   int
	}{
		{"RiichiStickValue", rules.RiichiStickValue, score.RiichiSticksBonus(1)},
		{"HonbaTsumoBonusPerLoser", rules.HonbaTsumoBonusPerLoser, score.HonbaBonus(score.WinTsumo, 1)},
		{"HonbaRonBonus", rules.HonbaRonBonus, score.HonbaBonus(score.WinRon, 1)},
	} {
		if tc.constant != tc.helper {
			t.Errorf("rules.%s = %d, the scoring helper gives %d", tc.name, tc.constant, tc.helper)
		}
	}
}

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
		if got := tc.win.IsTsumo(); got != tc.want {
			t.Errorf("Win(%d).IsTsumo() = %v, want %v", tc.win, got, tc.want)
		}
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
		situation := score.Situation{Win: score.WinRon, SeatWind: tc.seatWind, RoundWind: tc.roundWind}
		if got := situation.IsDealer(); got != tc.want {
			t.Errorf("IsDealer() with seat %v, round %v = %v, want %v", tc.seatWind, tc.roundWind, got, tc.want)
		}
	}
}
