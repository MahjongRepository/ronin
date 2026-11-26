package messaging_test

import (
	"encoding/hex"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func timerSettings() messaging.TimerSettings {
	return messaging.TimerSettings{BaseTurn: 5, Bank: 20, MaxBank: 20, RoundAdvanceTimeout: 10, GameStartConfirm: 3}
}

func TestSessionMessages_ShouldEncodeToTheGoldenBytes(t *testing.T) {
	for _, c := range []struct {
		name    string
		message wire.Map
		hex     string
	}{
		{
			"session_error",
			messaging.SessionError(messaging.SessionRateLimited, "Too many messages", play.Some(12)),
			"846cad73657373696f6e5f6572726f7250ac726174655f6c696d697465645cb1546f6f206d616e79206d657373616765736d0c",
		},
		{"pong", messaging.Pong(), "816ca4706f6e67"},
	} {
		t.Run(c.name, func(t *testing.T) {
			got, err := wire.Encode(c.message)
			if err != nil || hex.EncodeToString(got) != c.hex {
				t.Errorf("%s: Encode = %x, %v; want %s", c.name, got, err, c.hex)
			}
		})
	}
}

func TestSessionMessages_ShouldNameOnlyWhatTheyCarry(t *testing.T) {
	for _, c := range []struct {
		name string
		got  wire.Map
		want wire.Map
	}{
		{"error without a wait id", messaging.SessionError(messaging.SessionInvalidMessage, "bad", play.Option[int]{}), wire.Map{
			{Key: wire.KeySessionType, Value: wire.Str("session_error")},
			{Key: wire.KeySessionErrorCode, Value: wire.Str("invalid_message")},
			{Key: wire.KeySessionErrorMessage, Value: wire.Str("bad")},
		}},
		{"game joined", messaging.GameJoined(30), wire.Map{
			{Key: wire.KeySessionType, Value: wire.Str("game_joined")},
			{Key: wire.KeyPendingGameTimeout, Value: wire.Float(30)},
		}},
		{"stand-in", messaging.SeatControl(seat(t, 2), play.Some(wire.SeatControlLeft)), wire.Map{
			{Key: wire.KeySessionType, Value: wire.Str("seat_control")},
			{Key: wire.KeySeat, Value: wire.Int(2)},
			{Key: wire.KeySeatControlReason, Value: wire.Int(0)},
		}},
		{"return", messaging.SeatControl(seat(t, 2), play.Option[wire.SeatControlReason]{}), wire.Map{
			{Key: wire.KeySessionType, Value: wire.Str("seat_control")},
			{Key: wire.KeySeat, Value: wire.Int(2)},
		}},
	} {
		t.Run(c.name, func(t *testing.T) {
			assertMap(t, c.name, c.got, c.want)
		})
	}
}

func TestStampOpening_WhenReSent_ShouldNameTheElapsedTimeThenTheWaitAndAWholeBankAsAnInteger(t *testing.T) {
	opening := wire.Map{{Key: wire.KeyEventType, Value: wire.Int(12)}}

	stamped := messaging.StampOpening(opening, 3, messaging.WholeSeconds(20), play.Some(1.5))
	fractional := messaging.StampOpening(opening, 3, messaging.FractionalSeconds(20), play.Option[float64]{})

	assertMap(t, "re-sent opening", stamped, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(12)},
		{Key: wire.KeyWaitElapsed, Value: wire.Float(1.5)},
		{Key: wire.KeyWaitID, Value: wire.Int(3)},
		{Key: wire.KeyBankSeconds, Value: wire.Int(20)},
	})
	assertMap(t, "first opening", fractional, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(12)},
		{Key: wire.KeyWaitID, Value: wire.Int(3)},
		{Key: wire.KeyBankSeconds, Value: wire.Float(20)},
	})
	assertMap(t, "opening", opening, wire.Map{{Key: wire.KeyEventType, Value: wire.Int(12)}})
}

func TestGameReconnected_WhenTheSeatOwesARunningConfirmation_ShouldNameItsTimerBeforeTheTimerSettings(t *testing.T) {
	snapshot := wire.Map{{Key: wire.KeyGameID, Value: wire.Str("game1")}}
	running := play.Some(messaging.Pause{
		Owed: true, Timer: play.Some(messaging.PauseTimer{Elapsed: 1.25, Timeout: messaging.WholeSeconds(20)}),
	})

	owed := messaging.GameReconnected(snapshot, 2, running, timerSettings())
	confirmed := messaging.GameReconnected(snapshot, 2, play.Some(messaging.Pause{
		Timer: running.Value.Timer,
	}), timerSettings())
	playing := messaging.GameReconnected(snapshot, 2, play.Option[messaging.Pause]{}, timerSettings())

	timer := wire.Field{Key: wire.KeyTimerSettings, Value: wire.Map{
		{Key: wire.KeyBaseTurnSeconds, Value: wire.Float(5)},
		{Key: wire.KeyBankSeconds, Value: wire.Float(20)},
		{Key: wire.KeyMaxBankSeconds, Value: wire.Float(20)},
		{Key: wire.KeyRoundAdvanceTimeout, Value: wire.Float(10)},
		{Key: wire.KeyGameStartConfirm, Value: wire.Float(3)},
	}}
	head := wire.Map{
		{Key: wire.KeyGameID, Value: wire.Str("game1")},
		{Key: wire.KeySessionType, Value: wire.Str("game_reconnected")},
		{Key: wire.KeyWaitID, Value: wire.Int(2)},
	}
	assertMap(t, "owed", owed, append(append(wire.Map{}, head...),
		wire.Field{Key: wire.KeyConfirmationOwed, Value: wire.Bool(true)},
		wire.Field{Key: wire.KeyWaitElapsed, Value: wire.Float(1.25)},
		wire.Field{Key: wire.KeyRoundAdvanceSeconds, Value: wire.Int(20)},
		timer))
	assertMap(t, "confirmed", confirmed, append(append(wire.Map{}, head...),
		wire.Field{Key: wire.KeyConfirmationOwed, Value: wire.Bool(false)}, timer))
	assertMap(t, "playing", playing, append(append(wire.Map{}, head...), timer))
}

func TestStampPause_ShouldNameTheRecipientsWaitAndThePausesTimeout(t *testing.T) {
	roundEnd := wire.Map{{Key: wire.KeyEventType, Value: wire.Int(4)}}

	stamped := messaging.StampPause(roundEnd, 5, messaging.WholeSeconds(30))

	assertMap(t, "round end", stamped, wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(4)},
		{Key: wire.KeyWaitID, Value: wire.Int(5)},
		{Key: wire.KeyRoundAdvanceSeconds, Value: wire.Int(30)},
	})
}
