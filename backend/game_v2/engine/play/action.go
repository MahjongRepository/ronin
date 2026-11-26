package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// KanKind is which kan a kan action declares.
type KanKind uint8

const (
	KanClosed KanKind = iota
	KanAdded
	KanOpen
)

// ActionKind is what an Action does. It starts at 1, so the zero Action is no action.
type ActionKind uint8

const (
	ActionDiscard ActionKind = iota + 1
	ActionRiichi
	ActionTsumo
	ActionRon
	ActionKyuushu
	ActionPass
	ActionPon
	ActionChi
	ActionKan
)

// Action is one answer of a seat to the game. It is comparable, and two actions built alike are
// equal: a kind's unused payload is always zero. Build one with the constructor of its kind.
type Action struct {
	kind  ActionKind
	tiles [2]tile.TileID
	kan   KanKind
}

// DiscardAction discards this exact held tile.
func DiscardAction(t tile.TileID) Action {
	return Action{kind: ActionDiscard, tiles: [2]tile.TileID{t}}
}

// RiichiAction declares riichi and discards this exact held tile, one whose discard keeps the hand
// tenpai.
func RiichiAction(t tile.TileID) Action {
	return Action{kind: ActionRiichi, tiles: [2]tile.TileID{t}}
}

// TsumoAction wins on the tile just drawn.
func TsumoAction() Action {
	return Action{kind: ActionTsumo}
}

// RonAction wins on the tile of the call prompt.
func RonAction() Action {
	return Action{kind: ActionRon}
}

// KyuushuAction aborts the round on a first turn with nine kinds of terminals and honors.
func KyuushuAction() Action {
	return Action{kind: ActionKyuushu}
}

// PassAction declines every call the prompt offers.
func PassAction() Action {
	return Action{kind: ActionPass}
}

// PonAction calls the prompt's tile into a triplet with these two held copies of its kind, any
// pair of the offered look.
func PonAction(held [2]tile.TileID) Action {
	return Action{kind: ActionPon, tiles: held}
}

// ChiAction calls the prompt's tile into a sequence with these two held tiles: any copies of an
// offered shape, a red five making its own shape.
func ChiAction(held [2]tile.TileID) Action {
	return Action{kind: ActionChi, tiles: held}
}

// KanAction declares a kan of kind of t's kind: any id of an offered kind, the engine taking the
// copies itself.
func KanAction(kind KanKind, t tile.TileID) Action {
	return Action{kind: ActionKan, tiles: [2]tile.TileID{t}, kan: kind}
}

// Kind returns what a does.
func (a Action) Kind() ActionKind {
	return a.kind
}

// Tile returns the tile of a discard, riichi or kan; false for any other kind.
func (a Action) Tile() (tile.TileID, bool) {
	if a.kind != ActionDiscard && a.kind != ActionRiichi && a.kind != ActionKan {
		return tile.TileID{}, false
	}

	return a.tiles[0], true
}

// Held returns the two held tiles of a pon or chi; false for any other kind.
func (a Action) Held() ([2]tile.TileID, bool) {
	if a.kind != ActionPon && a.kind != ActionChi {
		return [2]tile.TileID{}, false
	}

	return a.tiles, true
}

// Kan returns which kan a kan action declares; false for any other kind.
func (a Action) Kan() (KanKind, bool) {
	return a.kan, a.kind == ActionKan
}

// AnswersCall reports whether a answers a call prompt rather than plays a turn: a ron, a pass, a
// pon, a chi or an open kan. A closed or added kan is a turn action.
func (a Action) AnswersCall() bool {
	switch a.kind {
	case ActionRon, ActionPass, ActionPon, ActionChi:
		return true
	case ActionKan:
		return a.kan == KanOpen
	case ActionDiscard, ActionRiichi, ActionTsumo, ActionKyuushu:
	}

	return false
}
