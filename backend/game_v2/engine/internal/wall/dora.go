package wall

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// AddDoraIndicator reveals the next dora indicator and returns it. An IndicatorsExhaustedError
// when the revealed and pending indicators already make five.
func (w *Wall) AddDoraIndicator() (tile.TileID, error) {
	if w.revealed+w.pending >= indicatorStacks {
		return tile.TileID{}, IndicatorsExhaustedError{}
	}

	w.revealed++
	return w.indicators[w.revealed-1].Top, nil
}

func (w *Wall) IncrementPendingDora() error {
	if w.revealed+w.pending >= indicatorStacks {
		return IndicatorsExhaustedError{}
	}

	w.pending++
	return nil
}

// RevealPendingDora reveals every deferred kan dora and returns them in reveal order.
func (w *Wall) RevealPendingDora() []tile.TileID {
	first := w.revealed
	w.revealed += w.pending
	w.pending = 0
	return tops(w.indicators[first:w.revealed])
}

// ClearPendingDora drops the deferred kan dora reveals without revealing them, as a tsumo on the
// rinshan tile scores before they show.
func (w *Wall) ClearPendingDora() {
	w.pending = 0
}

// DoraIndicators returns the revealed dora indicators, in reveal order.
func (w Wall) DoraIndicators() []tile.TileID {
	return tops(w.indicators[:w.revealed])
}

// UraIndicators returns the ura dora indicators a riichi winner counts: the one under each
// revealed indicator, as kan ura dora (has_kan_uradora) is on.
func (w Wall) UraIndicators() []tile.TileID {
	ura := make([]tile.TileID, 0, w.revealed)
	for _, s := range w.indicators[:w.revealed] {
		ura = append(ura, s.Bottom)
	}

	return ura
}

func tops(stacks []Stack) []tile.TileID {
	ids := make([]tile.TileID, 0, len(stacks))
	for _, s := range stacks {
		ids = append(ids, s.Top)
	}

	return ids
}
