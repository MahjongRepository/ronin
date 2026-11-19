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
		{"double ron", play.Ron{Wins: []play.WinResult{first, second}}, [tile.SeatCount]int{-11900, 8000, 3900, 0}},
		{"tsumo", play.Tsumo{Win: second}, second.ScoreChanges},
		{"exhaustive draw", play.ExhaustiveDraw{ScoreChanges: [tile.SeatCount]int{1500, 1500, -1500, -1500}}, [tile.SeatCount]int{1500, 1500, -1500, -1500}},
		{"abortive", play.Abortive{Kind: play.FourWinds{}}, [tile.SeatCount]int{}},
	} {
		if got := c.result.TotalScoreChanges(); got != c.want {
			t.Errorf("%s TotalScoreChanges = %v, want %v", c.name, got, c.want)
		}
	}
}
