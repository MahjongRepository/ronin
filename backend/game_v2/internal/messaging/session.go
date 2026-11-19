package messaging

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// SessionErrorCode is why the session refused a client's message, the value of
// wire.KeySessionErrorCode.
type SessionErrorCode string

// The session error codes.
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
	pongType            = "pong"
)

// Seconds is a time in seconds as a message carries it: a whole number of seconds goes out as an
// integer, a fraction as a float, and the wire tells the two apart. Its zero value is 0 whole
// seconds.
type Seconds struct {
	fraction play.Option[float64]
	whole    int
}

// WholeSeconds returns n seconds, sent as an integer.
func WholeSeconds(n int) Seconds {
	return Seconds{whole: n}
}

// FractionalSeconds returns s seconds, sent as a float even when whole.
func FractionalSeconds(s float64) Seconds {
	return Seconds{fraction: play.Some(s)}
}

func (s Seconds) value() wire.Value {
	if s.fraction.OK {
		return wire.Float(s.fraction.Value)
	}
	return wire.Int(s.whole)
}

// SessionError returns a session error: its code and message, and for a refused game action the
// wait id it echoed, so the client matches the refusal to its own request.
func SessionError(code SessionErrorCode, message string, waitID play.Option[int]) wire.Map {
	m := wire.Map{
		{Key: wire.KeySessionType, Value: wire.Str(sessionErrorType)},
		{Key: wire.KeySessionErrorCode, Value: wire.Str(code)},
		{Key: wire.KeySessionErrorMessage, Value: wire.Str(message)},
	}
	return optionField(m, wire.KeyWaitID, waitID, func(id int) wire.Value { return wire.Int(id) })
}

// GameJoined returns the answer to an accepted join: how long, in seconds, the pending game waits
// for its players before it starts without them, the longest the server stays silent before it.
func GameJoined(pendingGameTimeout float64) wire.Map {
	return wire.Map{
		{Key: wire.KeySessionType, Value: wire.Str(gameJoinedType)},
		{Key: wire.KeyPendingGameTimeout, Value: wire.Float(pendingGameTimeout)},
	}
}

// SeatControl returns the message that seat changed hands: an AI player stands in for its
// participant for reason, or, without one, the participant took the seat back.
func SeatControl(seat tile.Seat, reason play.Option[wire.SeatControlReason]) wire.Map {
	m := wire.Map{
		{Key: wire.KeySessionType, Value: wire.Str(seatControlType)},
		{Key: wire.KeySeat, Value: seatValue(seat)},
	}
	return optionField(m, wire.KeySeatControlReason, reason, func(r wire.SeatControlReason) wire.Value {
		return wire.Int(r)
	})
}

// Pong returns the answer to a ping.
func Pong() wire.Map {
	return wire.Map{{Key: wire.KeySessionType, Value: wire.Str(pongType)}}
}

// TimerSettings is a seat's pacing in seconds: the base time of a turn or call, the seat's bank
// now and in full, the round advance timeout per result shown, and the game start confirmation's
// timeout. Each goes out as a float.
type TimerSettings struct {
	BaseTurn            float64
	Bank                float64
	MaxBank             float64
	RoundAdvanceTimeout float64
	GameStartConfirm    float64
}

// Payload returns s as the map wire.KeyTimerSettings holds.
func (s TimerSettings) Payload() wire.Map {
	return wire.Map{
		{Key: wire.KeyBaseTurnSeconds, Value: wire.Float(s.BaseTurn)},
		{Key: wire.KeyBankSeconds, Value: wire.Float(s.Bank)},
		{Key: wire.KeyMaxBankSeconds, Value: wire.Float(s.MaxBank)},
		{Key: wire.KeyRoundAdvanceTimeout, Value: wire.Float(s.RoundAdvanceTimeout)},
		{Key: wire.KeyGameStartConfirm, Value: wire.Float(s.GameStartConfirm)},
	}
}

// StampViewerSeat returns a copy of a broadcast message naming its recipient's seat, as each copy
// of the game start does.
func StampViewerSeat(m wire.Map, seat tile.Seat) wire.Map {
	return with(m, wire.KeySeat, seatValue(seat))
}

// StampTimerSettings returns a copy of m carrying its recipient's timer settings, as the game start
// and the reconnect snapshot do.
func StampTimerSettings(m wire.Map, timer TimerSettings) wire.Map {
	return with(m, wire.KeyTimerSettings, timer.Payload())
}

// StampPause returns a copy of the message that opens a pause for its recipient, a round end or
// the deal of the game start's confirmation: the recipient's wait id and the pause's whole
// timeout.
func StampPause(m wire.Map, waitID int, timeout Seconds) wire.Map {
	return with(with(m, wire.KeyWaitID, wire.Int(waitID)), wire.KeyRoundAdvanceSeconds, timeout.value())
}

// Pause is a seat's part in the pause a reconnect finds its game in: whether it still owes its
// confirmation and, while that confirmation's timer runs, the timer.
type Pause struct {
	Owed  bool
	Timer play.Option[PauseTimer]
}

// PauseTimer is how long the timer of a seat's owed confirmation has run, in seconds, and its
// whole timeout.
type PauseTimer struct {
	Elapsed float64
	Timeout Seconds
}

// GameReconnected returns the game_reconnected message from a seat's reconnect snapshot: the
// participant's latest wait id, its part in the pause the game is in, and its timer settings. The
// timer of an owed confirmation names how long it has run and its whole timeout; a seat that owes
// nothing names neither.
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
