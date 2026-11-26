package messaging

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type SessionErrorCode string

const (
	SessionAlreadyInGame          SessionErrorCode = "already_in_game"
	SessionNotInGame              SessionErrorCode = "not_in_game"
	SessionGameNotStarted         SessionErrorCode = "game_not_started"
	SessionInvalidMessage         SessionErrorCode = "invalid_message"
	SessionInternalError          SessionErrorCode = "internal_error"
	SessionReconnectNoSession     SessionErrorCode = "reconnect_no_session"
	SessionReconnectGameMismatch  SessionErrorCode = "reconnect_game_mismatch"
	SessionReconnectRetryLater    SessionErrorCode = "reconnect_retry_later"
	SessionReconnectAlreadyActive SessionErrorCode = "reconnect_already_active"
	SessionInvalidTicket          SessionErrorCode = "invalid_ticket"
	SessionJoinGameNotFound       SessionErrorCode = "join_game_not_found"
	SessionJoinGameAlreadyStarted SessionErrorCode = "join_game_already_started"
	SessionJoinGameNoSession      SessionErrorCode = "join_game_no_session"
	SessionRateLimited            SessionErrorCode = "rate_limited"
)

const (
	sessionErrorType    = "session_error"
	gameJoinedType      = "game_joined"
	gameReconnectedType = "game_reconnected"
	seatControlType     = "seat_control"
	callClosedType      = "call_closed"
	pongType            = "pong"
)

type Seconds struct {
	fraction play.Option[float64]
	whole    int
}

func WholeSeconds(n int) Seconds {
	return Seconds{whole: n}
}

func FractionalSeconds(s float64) Seconds {
	return Seconds{fraction: play.Some(s)}
}

func (s Seconds) value() wire.Value {
	if s.fraction.OK {
		return wire.Float(s.fraction.Value)
	}
	return wire.Int(s.whole)
}

func SessionError(code SessionErrorCode, message string, waitID play.Option[int]) wire.Map {
	m := wire.Map{
		{Key: wire.KeySessionType, Value: wire.Str(sessionErrorType)},
		{Key: wire.KeySessionErrorCode, Value: wire.Str(code)},
		{Key: wire.KeySessionErrorMessage, Value: wire.Str(message)},
	}
	return optionField(m, wire.KeyWaitID, waitID, func(id int) wire.Value { return wire.Int(id) })
}

func GameJoined(pendingGameTimeout float64) wire.Map {
	return wire.Map{
		{Key: wire.KeySessionType, Value: wire.Str(gameJoinedType)},
		{Key: wire.KeyPendingGameTimeout, Value: wire.Float(pendingGameTimeout)},
	}
}

func SeatControl(seat tile.Seat, reason play.Option[wire.SeatControlReason]) wire.Map {
	m := wire.Map{
		{Key: wire.KeySessionType, Value: wire.Str(seatControlType)},
		{Key: wire.KeySeat, Value: seatValue(seat)},
	}
	return optionField(m, wire.KeySeatControlReason, reason, func(r wire.SeatControlReason) wire.Value {
		return wire.Int(r)
	})
}

func CallClosed() wire.Map {
	return wire.Map{{Key: wire.KeySessionType, Value: wire.Str(callClosedType)}}
}

func Pong() wire.Map {
	return wire.Map{{Key: wire.KeySessionType, Value: wire.Str(pongType)}}
}

type TimerSettings struct {
	BaseTurn            float64
	Bank                float64
	MaxBank             float64
	RoundAdvanceTimeout float64
	GameStartConfirm    float64
}

func (s TimerSettings) Payload() wire.Map {
	return wire.Map{
		{Key: wire.KeyBaseTurnSeconds, Value: wire.Float(s.BaseTurn)},
		{Key: wire.KeyBankSeconds, Value: wire.Float(s.Bank)},
		{Key: wire.KeyMaxBankSeconds, Value: wire.Float(s.MaxBank)},
		{Key: wire.KeyRoundAdvanceTimeout, Value: wire.Float(s.RoundAdvanceTimeout)},
		{Key: wire.KeyGameStartConfirm, Value: wire.Float(s.GameStartConfirm)},
	}
}

func StampViewerSeat(m wire.Map, seat tile.Seat) wire.Map {
	return with(m, wire.KeySeat, seatValue(seat))
}

func StampTimerSettings(m wire.Map, timer TimerSettings) wire.Map {
	return with(m, wire.KeyTimerSettings, timer.Payload())
}

func StampPause(m wire.Map, waitID int, timeout Seconds) wire.Map {
	return withAll(m,
		wire.Field{Key: wire.KeyWaitID, Value: wire.Int(waitID)},
		wire.Field{Key: wire.KeyRoundAdvanceSeconds, Value: timeout.value()})
}

type Pause struct {
	Owed  bool
	Timer play.Option[PauseTimer]
}

type PauseTimer struct {
	Elapsed float64
	Timeout Seconds
}

func GameReconnected(snapshot wire.Map, waitID int, pause play.Option[Pause], timer TimerSettings) wire.Map {
	m := with(snapshot, wire.KeySessionType, wire.Str(gameReconnectedType))
	m = with(m, wire.KeyWaitID, wire.Int(waitID))
	if pause.OK {
		m = with(m, wire.KeyConfirmationOwed, wire.Bool(pause.Value.Owed))
		if running := pause.Value.Timer; pause.Value.Owed && running.OK {
			m = with(m, wire.KeyWaitElapsed, wire.Float(running.Value.Elapsed))
			m = with(m, wire.KeyRoundAdvanceSeconds, running.Value.Timeout.value())
		}
	}
	return StampTimerSettings(m, timer)
}
