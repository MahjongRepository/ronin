package play_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestAction_ShouldCarryOnlyThePayloadOfItsKind(t *testing.T) {
	discarded, held := id(t, 5), [2]tile.TileID{id(t, 9), id(t, 10)}
	for _, c := range []struct {
		name     string
		action   play.Action
		kind     play.ActionKind
		tile     tile.TileID
		hasTile  bool
		held     [2]tile.TileID
		hasHeld  bool
		kan      play.KanKind
		isKanned bool
	}{
		{"discard", play.DiscardAction(discarded), play.ActionDiscard, discarded, true, [2]tile.TileID{}, false, 0, false},
		{"riichi", play.RiichiAction(discarded), play.ActionRiichi, discarded, true, [2]tile.TileID{}, false, 0, false},
		{"tsumo", play.TsumoAction(), play.ActionTsumo, tile.TileID{}, false, [2]tile.TileID{}, false, 0, false},
		{"ron", play.RonAction(), play.ActionRon, tile.TileID{}, false, [2]tile.TileID{}, false, 0, false},
		{"kyuushu", play.KyuushuAction(), play.ActionKyuushu, tile.TileID{}, false, [2]tile.TileID{}, false, 0, false},
		{"pass", play.PassAction(), play.ActionPass, tile.TileID{}, false, [2]tile.TileID{}, false, 0, false},
		{"pon", play.PonAction(held), play.ActionPon, tile.TileID{}, false, held, true, 0, false},
		{"chi", play.ChiAction(held), play.ActionChi, tile.TileID{}, false, held, true, 0, false},
		{"kan", play.KanAction(play.KanAdded, discarded), play.ActionKan, discarded, true, [2]tile.TileID{}, false, play.KanAdded, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.action.Kind(); got != c.kind {
				t.Errorf("Kind = %d, want %d", got, c.kind)
			}
			if got, ok := c.action.Tile(); got != c.tile || ok != c.hasTile {
				t.Errorf("Tile = %v, %t, want %v, %t", got, ok, c.tile, c.hasTile)
			}
			if got, ok := c.action.Held(); got != c.held || ok != c.hasHeld {
				t.Errorf("Held = %v, %t, want %v, %t", got, ok, c.held, c.hasHeld)
			}
			if got, ok := c.action.Kan(); got != c.kan || ok != c.isKanned {
				t.Errorf("Kan = %d, %t, want %d, %t", got, ok, c.kan, c.isKanned)
			}
		})
	}
}

func TestAction_WhenBuiltAlike_ShouldBeEqual(t *testing.T) {
	first, second := play.DiscardAction(id(t, 7)), play.DiscardAction(id(t, 7))
	if first != second {
		t.Error("two discards of one tile differ")
	}
	if play.DiscardAction(id(t, 7)) == play.RiichiAction(id(t, 7)) {
		t.Error("a discard equals a riichi of the same tile")
	}
	if play.KanAction(play.KanClosed, id(t, 0)) == play.KanAction(play.KanAdded, id(t, 0)) {
		t.Error("a closed kan equals an added kan of the same tile")
	}
	if (play.Action{}) == play.DiscardAction(id(t, 0)) {
		t.Error("the zero Action is a discard of tile 0")
	}
}
