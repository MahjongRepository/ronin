package messaging

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type GameErrorCode string

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

type GameError struct {
	Code    GameErrorCode
	Message string
	WaitID  int
}

func (e GameError) Payload() wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventError)},
		{Key: wire.KeyGameErrorCode, Value: wire.Str(e.Code)},
		{Key: wire.KeyGameErrorMessage, Value: wire.Str(e.Message)},
		{Key: wire.KeyWaitID, Value: wire.Int(e.WaitID)},
	}
}

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

func CalledTileMismatch(action play.Action, waitID int) GameError {
	return GameError{Code: invalidCode(action), Message: "tile_id mismatch", WaitID: waitID}
}

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
