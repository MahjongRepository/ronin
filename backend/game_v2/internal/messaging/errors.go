package messaging

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// GameErrorCode is why a seat's game action was refused, the value of wire.KeyGameErrorCode; the
// action changed nothing.
type GameErrorCode string

// The game error codes.
const (
	GameNotYourTurn    GameErrorCode = "not_your_turn"
	GameInvalidDiscard GameErrorCode = "invalid_discard"
	GameInvalidRiichi  GameErrorCode = "invalid_riichi"
	GameInvalidRon     GameErrorCode = "invalid_ron"
	GameInvalidPon     GameErrorCode = "invalid_pon"
	GameInvalidChi     GameErrorCode = "invalid_chi"
	GameInvalidKan     GameErrorCode = "invalid_kan"
	GameInvalidPass    GameErrorCode = "invalid_pass"
	GameInvalidAction  GameErrorCode = "invalid_action"
	GameStaleAction    GameErrorCode = "stale_action"
)

// GameError is the error message to a seat whose game action was refused, naming the wait id that
// action echoed, never the current wait's.
type GameError struct {
	Code    GameErrorCode
	Message string
	WaitID  int
}

// Payload returns e as its message.
func (e GameError) Payload() wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventError)},
		{Key: wire.KeyGameErrorCode, Value: wire.Str(e.Code)},
		{Key: wire.KeyGameErrorMessage, Value: wire.Str(e.Message)},
		{Key: wire.KeyWaitID, Value: wire.Int(e.WaitID)},
	}
}

// RefusalError returns the game error answering action, which the engine refused, so the client
// never reads the engine's refusal codes: a round not in play is an invalid action; a seat the
// engine does not await gets "not your turn" for a turn action and the action's own invalid code
// for a call answer or pass; a discard kuikae or riichi forbids, or a riichi discard that breaks
// tenpai, names its tile. False for any other refusal, input no client builds (a tile not held, an
// action not offered), which the session treats as a protocol violation.
func RefusalError(action play.Action, refusal play.Refusal, waitID int) (GameError, bool) {
	refused := GameError{WaitID: waitID}
	switch {
	case refusal.Code == play.CodeWrongPhase:
		refused.Code, refused.Message = GameInvalidAction, "round is not in progress"
	case refusal.Kind == play.RefusalNotAwaited && answersACall(action):
		refused.Code, refused.Message = invalidCode(action), "no pending call prompt"
	case refusal.Kind == play.RefusalNotAwaited:
		refused.Code, refused.Message = GameNotYourTurn, "not your turn"
	default:
		return ruleError(action, refusal, refused)
	}
	return refused, true
}

func ruleError(action play.Action, refusal play.Refusal, refused GameError) (GameError, bool) {
	id, holdsTile := action.Tile()
	isDiscard := action.Kind() == play.ActionDiscard || action.Kind() == play.ActionRiichi
	if refusal.Kind != play.RefusalRule || !holdsTile || !isDiscard {
		return GameError{}, false
	}

	tileName := strconv.Itoa(id.Index())
	switch refusal.Code {
	case play.CodeKuikae, play.CodeRiichiDrawnTileOnly:
		refused.Code = GameInvalidDiscard
		refused.Message = "tile " + tileName + " is not a legal discard (kuikae or riichi tsumogiri)"
	case play.CodeRiichiBreaksTenpai:
		refused.Code, refused.Message = GameInvalidRiichi, "hand is not tenpai after discarding tile "+tileName
	case play.CodeTileNotHeld, play.CodeNotOffered, play.CodeWrongPhase, play.CodeSeatNotAwaited,
		play.CodeAlreadyAnswered:
		return GameError{}, false
	}
	return refused, true
}

// CalledTileMismatch returns the game error answering a pon, chi or open kan whose called tile is
// not the open call's: the answer's own invalid code.
func CalledTileMismatch(action play.Action, waitID int) GameError {
	return GameError{Code: invalidCode(action), Message: "tile_id mismatch", WaitID: waitID}
}

// StaleAction returns the game error answering an action or a confirmation for a decision that is
// not the seat's current one.
func StaleAction(waitID int) GameError {
	return GameError{Code: GameStaleAction, Message: "the wait this action answers has already ended", WaitID: waitID}
}

func answersACall(action play.Action) bool {
	switch action.Kind() {
	case play.ActionRon, play.ActionPon, play.ActionChi, play.ActionPass:
		return true
	case play.ActionKan:
		kind, _ := action.Kan()
		return kind == play.KanOpen
	case play.ActionDiscard, play.ActionRiichi, play.ActionTsumo, play.ActionKyuushu:
	}
	return false
}

func invalidCode(action play.Action) GameErrorCode {
	switch action.Kind() {
	case play.ActionDiscard:
		return GameInvalidDiscard
	case play.ActionRiichi:
		return GameInvalidRiichi
	case play.ActionRon:
		return GameInvalidRon
	case play.ActionPon:
		return GameInvalidPon
	case play.ActionChi:
		return GameInvalidChi
	case play.ActionKan:
		return GameInvalidKan
	case play.ActionPass:
		return GameInvalidPass
	case play.ActionTsumo, play.ActionKyuushu:
	}
	return GameInvalidAction
}
