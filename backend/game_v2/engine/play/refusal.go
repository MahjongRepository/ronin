package play

import "strconv"

// RefusalKind is which kind of mistake a Refusal reports: a held tile or an offered action that a
// rule forbids now; structurally impossible input, a tile not held or an action the seat was not
// offered; or a call in the wrong phase, or an action from a seat the engine is not waiting on.
type RefusalKind uint8

const (
	RefusalRule RefusalKind = iota
	RefusalNotOffered
	RefusalNotAwaited
)

// String returns k's snake_case identifier.
func (k RefusalKind) String() string {
	switch k {
	case RefusalRule:
		return "rule"
	case RefusalNotOffered:
		return "not_offered"
	case RefusalNotAwaited:
		return "not_awaited"
	default:
		return "play.RefusalKind(" + strconv.Itoa(int(k)) + ")"
	}
}

// RefusalCode is what exactly a Refusal refused.
type RefusalCode uint8

const (
	CodeTileNotHeld RefusalCode = iota
	CodeNotOffered
	CodeWrongPhase
	CodeSeatNotAwaited
	CodeAlreadyAnswered
	CodeRiichiDrawnTileOnly
	CodeRiichiBreaksTenpai
	CodeKuikae
)

// String returns c's snake_case identifier.
func (c RefusalCode) String() string {
	switch c {
	case CodeTileNotHeld:
		return "tile_not_held"
	case CodeNotOffered:
		return "not_offered"
	case CodeWrongPhase:
		return "wrong_phase"
	case CodeSeatNotAwaited:
		return "seat_not_awaited"
	case CodeAlreadyAnswered:
		return "already_answered"
	case CodeRiichiDrawnTileOnly:
		return "riichi_drawn_tile_only"
	case CodeRiichiBreaksTenpai:
		return "riichi_breaks_tenpai"
	case CodeKuikae:
		return "kuikae"
	default:
		return "play.RefusalCode(" + strconv.Itoa(int(c)) + ")"
	}
}

// Refusal is an action the game did not accept: its kind and what was refused. A refused action
// leaves the game unchanged. It is a domain outcome, not an error.
type Refusal struct {
	Kind RefusalKind
	Code RefusalCode
}
