package seam_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestSettle_WhenTheWinIsTheOtherKind_ShouldReturnAMisfitWinError(t *testing.T) {
	_, tsumoErr := engine.SettleTsumo(engine.Table{}, engine.WinningHand{Win: engine.WinRon})
	_, ronErr := engine.SettleRon(engine.Table{}, tile.Seats()[1], []engine.WinningHand{{Win: engine.WinTsumo}})

	for name, c := range map[string]struct {
		err  error
		want string
	}{
		"ron settled as a tsumo": {tsumoErr, "a ron win cannot be settled as a tsumo"},
		"tsumo settled as a ron": {ronErr, "a tsumo win cannot be settled as a ron"},
	} {
		if _, ok := errors.AsType[engine.MisfitWinError](c.err); !ok || c.err.Error() != c.want {
			t.Errorf("%s: error = %v, want MisfitWinError %q", name, c.err, c.want)
		}
	}
}
