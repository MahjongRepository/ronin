package seam_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestSettle_WhenTheWinIsTheOtherKind_ShouldReturnAMisfitWinError(t *testing.T) {
	_, tsumoErr := engine.SettleTsumo(engine.Table{}, engine.WinningHand{Win: engine.WinRon})
	_, ronErr := engine.SettleRon(engine.Table{}, tile.Seats()[1], []engine.WinningHand{{Win: engine.WinTsumo}})

	for _, c := range []struct {
		name string
		err  error
		want engine.Win
	}{
		{name: "ron settled as a tsumo", err: tsumoErr, want: engine.WinRon},
		{name: "tsumo settled as a ron", err: ronErr, want: engine.WinTsumo},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got, ok := errors.AsType[engine.MisfitWinError](c.err); !ok || got.Win != c.want {
				t.Errorf("error = %v, want MisfitWinError of win %v", c.err, c.want)
			}
		})
	}
}

func TestSettleRon_WhenTheTableHoldsFewerSticksThanTheRiichiWinners_ShouldRefuseIt(t *testing.T) {
	riichi := play.Some(play.Riichi{})
	winners := []engine.WinningHand{
		{Seat: tile.Seats()[2], Win: engine.WinRon},
		{Seat: tile.Seats()[3], Win: engine.WinRon, Riichi: riichi},
	}

	_, err := engine.SettleRon(engine.Table{Ruleset: play.RulesetRRC}, tile.Seats()[1], winners)
	if !errors.Is(err, engine.TooFewRiichiSticksError{RiichiSticks: 0, RiichiWinners: 1}) {
		t.Errorf("SettleRon error = %v, want TooFewRiichiSticksError", err)
	}
}
