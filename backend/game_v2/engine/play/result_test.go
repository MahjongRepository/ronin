package play_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestRoundResultTotalScoreChanges_ShouldAddEveryWinOfADoubleRon(t *testing.T) {
	first := play.WinResult{ScoreChanges: [tile.SeatCount]int{-8000, 8000, 0, 0}}
	second := play.WinResult{ScoreChanges: [tile.SeatCount]int{-3900, 0, 3900, 0}}

	for _, c := range []struct {
		name   string
		result play.RoundResult
		want   [tile.SeatCount]int
	}{
		{name: "double ron", result: play.Ron{Wins: []play.WinResult{first, second}}, want: [tile.SeatCount]int{-11900, 8000, 3900, 0}},
		{name: "tsumo", result: play.Tsumo{Win: second}, want: second.ScoreChanges},
		{name: "exhaustive draw", result: play.ExhaustiveDraw{ScoreChanges: [tile.SeatCount]int{1500, 1500, -1500, -1500}}, want: [tile.SeatCount]int{1500, 1500, -1500, -1500}},
		{name: "abortive", result: play.Abortive{Kind: play.FourWinds{}}},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.result.TotalScoreChanges(); got != c.want {
				t.Errorf("TotalScoreChanges = %v, want %v", got, c.want)
			}
		})
	}
}
