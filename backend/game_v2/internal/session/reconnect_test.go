package session_test

import (
	"testing"
	"testing/synctest"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func noStartPause(timing *session.Timing) {
	timing.GameStartConfirm = 0
}

func (h *harness) reconnect(ticket string) *fakeConn {
	conn := h.connect()
	h.m.Reconnect(conn, ticket)
	synctest.Wait()
	return conn
}

func reconnected(t *testing.T, conn *fakeConn) wire.Map {
	t.Helper()
	snapshots := ofSession(conn.messages(), "game_reconnected")
	if len(snapshots) != 1 {
		t.Fatalf("%s got %d game_reconnected, want 1", conn.id, len(snapshots))
	}
	return snapshots[0]
}

func sessionErrorCode(t *testing.T, conn *fakeConn) wire.Value {
	t.Helper()
	errs := ofSession(conn.messages(), "session_error")
	if len(errs) != 1 {
		t.Fatalf("%s got %d session errors, want 1", conn.id, len(errs))
	}
	code, _ := errs[0].Get(wire.KeySessionErrorCode)
	return code
}

func TestReconnect_WhenTheSeatLeftDuringItsTurn_ShouldTakeItBackOnItsOriginalDeadline(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t, withTiming(noStartPause))
		leftWaitID := intOf(t, lastDraw(t, alice), wire.KeyWaitID)

		sleep(15 * time.Second)
		h.m.Disconnect(alice)
		synctest.Wait()
		sleep(500 * time.Millisecond)
		back := h.reconnect("ticket-Alice")

		control := ofSession(bob.messages(), "seat_control")
		if len(control) != 2 {
			t.Fatalf("bob got %d seat_control, want the leave and the return", len(control))
		}
		if _, standIn := control[1].Get(wire.KeySeatControlReason); standIn {
			t.Errorf("bob's second seat_control = %v, want the seat back with its participant", control[1])
		}
		if got := intOf(t, reconnected(t, back), wire.KeyWaitID); got != leftWaitID+1 {
			t.Errorf("game_reconnected wait id = %d, want a new decision %d", got, leftWaitID+1)
		}
		opening := lastOpening(t, back)
		if got := intOf(t, opening, wire.KeyWaitID); got != leftWaitID+1 {
			t.Errorf("re-sent draw wait id = %d, want %d", got, leftWaitID+1)
		}
		if got, _ := opening.Get(wire.KeyBankSeconds); got != wire.Int(20) {
			t.Errorf("re-sent draw bank = %v, want the 20 not yet charged", got)
		}
		if got, _ := opening.Get(wire.KeyWaitElapsed); got != wire.Float(15.5) {
			t.Errorf("re-sent draw elapsed = %v, want 15.5 s counted from the turn's start", got)
		}

		sleep(time.Second)
		if got := len(ofEvent(bob.messages(), wire.EventDiscard)); got != 0 {
			t.Fatalf("the AI player discarded %d times after the seat was taken back", got)
		}
		sleep(13500*time.Millisecond - time.Millisecond)
		if got := h.m.Stats().TurnTimeouts; got != 0 {
			t.Fatalf("the turn timed out before its original deadline")
		}
		sleep(time.Millisecond)
		if got := h.m.Stats().TurnTimeouts; got != 1 {
			t.Errorf("TurnTimeouts = %d, want the turn timed out at its original 30 s", got)
		}
		if got := h.m.Stats().Reconnects; got != 1 {
			t.Errorf("Reconnects = %d, want 1", got)
		}
		h.assertSeatLogged(t, "player reconnected")
		h.assertSeatLogged(t, "player left game")
	})
}

func TestReconnect_WhenTheAIPlayedTheTurnTheSeatLeft_ShouldShowTheBankChargedOnlyUntilTheSeatLeft(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t, withTiming(noStartPause))

		sleep(15 * time.Second)
		h.m.Disconnect(alice)
		synctest.Wait()
		sleep(time.Second)
		if got := len(ofEvent(bob.messages(), wire.EventDiscard)); got != 1 {
			t.Fatalf("bob saw %d discards, want the AI player's one for the absent seat", got)
		}
		back := h.reconnect("ticket-Alice")

		settings, _ := reconnected(t, back).Get(wire.KeyTimerSettings)
		timer, ok := settings.(wire.Map)
		if !ok {
			t.Fatalf("game_reconnected timer settings = %v, want a map", settings)
		}
		if got, _ := timer.Get(wire.KeyBankSeconds); got != wire.Float(15) {
			t.Errorf("bank = %v, want the 15 left after the 5 s of overtime before the seat left", got)
		}
	})
}

func TestReconnect_WhenTheParticipantIsStillConnected_ShouldReplaceItsConnectionAndKeepTheWaitRunning(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t, withTiming(noStartPause))
		waitID := intOf(t, lastDraw(t, alice), wire.KeyWaitID)

		sleep(3 * time.Second)
		second := h.reconnect("ticket-Alice")

		if code, closed := alice.closeCode(); !closed || code != session.CloseReplaced {
			t.Errorf("first connection close = %v, %v, want 4002", code, closed)
		}
		if got := len(ofSession(bob.messages(), "seat_control")); got != 0 {
			t.Errorf("bob got %d seat_control for a seat that never changed hands", got)
		}
		opening := lastOpening(t, second)
		if got := intOf(t, opening, wire.KeyWaitID); got != waitID {
			t.Errorf("re-sent draw wait id = %d, want the open decision %d", got, waitID)
		}
		if got, _ := opening.Get(wire.KeyWaitElapsed); got != wire.Float(3) {
			t.Errorf("re-sent draw elapsed = %v, want 3 s", got)
		}

		sleep(27*time.Second - time.Millisecond)
		if got := h.m.Stats().TurnTimeouts; got != 0 {
			t.Fatalf("the turn timed out before its first deadline")
		}
		sleep(time.Millisecond)
		stats := h.m.Stats()
		if stats.TurnTimeouts != 1 || stats.Takeovers != 1 || stats.Reconnects != 0 {
			t.Errorf("stats = %+v, want one turn timeout and one takeover, no reconnect", stats)
		}
		h.assertSeatLogged(t, "connection taken over")
		h.assertSeatLogged(t, "replacing a participant's connection")
	})
}

func TestReconnect_WhenTheStartPauseHoldsTheDealersDraw_ShouldShowTheDealtHandAndTheOwedConfirmation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t)
		dealt := ofEvent(alice.messages(), wire.EventRoundStarted)[0]

		sleep(4 * time.Second)
		second := h.reconnect("ticket-Alice")

		messages := second.messages()
		if len(messages) != 1 {
			t.Fatalf("second connection got %d messages, want the snapshot alone", len(messages))
		}
		snapshot := reconnected(t, second)
		wantHand, _ := dealt.Get(wire.KeyMyTiles)
		gotHand, _ := snapshot.Get(wire.KeyMyTiles)
		if diff := cmp.Diff(wantHand, gotHand); diff != "" {
			t.Errorf("snapshot hand differs from the deal (-want +got):\n%s", diff)
		}
		for _, tc := range []struct {
			key  wire.Key
			want wire.Value
		}{
			{wire.KeyTilesRemaining, wire.Int(70)},
			{wire.KeyConfirmationOwed, wire.Bool(true)},
			{wire.KeyWaitElapsed, wire.Float(4)},
			{wire.KeyRoundAdvanceSeconds, wire.Int(10)},
		} {
			if got, _ := snapshot.Get(tc.key); got != tc.want {
				t.Errorf("snapshot %v = %v, want %v", tc.key, got, tc.want)
			}
		}

		h.act(second, confirmRound(intOf(t, snapshot, wire.KeyWaitID)))
		h.confirm(bob)
		if got := len(ofEvent(second.messages(), wire.EventDraw)); got != 1 {
			t.Errorf("the dealer got %d draws after both confirmed, want 1", got)
		}
	})
}

func TestReconnect_WhenItCannotTakeASeat_ShouldAnswerWhy(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.join("Alice")
		early := h.reconnect("ticket-Bob")
		bob := h.join("Bob")

		stranger := h.reconnect("ticket-Nobody")
		lost := &fakeConn{id: "conn-lost", gameID: "game-0404"}
		h.m.Connect(lost)
		h.m.Reconnect(lost, "ticket-Bob")
		h.m.Reconnect(alice, "ticket-Bob")
		synctest.Wait()

		for _, tc := range []struct {
			conn *fakeConn
			want messaging.SessionErrorCode
		}{
			{early, messaging.SessionReconnectRetryLater},
			{stranger, messaging.SessionReconnectNoSession},
			{lost, messaging.SessionReconnectGameMismatch},
			{alice, messaging.SessionReconnectAlreadyActive},
		} {
			if got := sessionErrorCode(t, tc.conn); got != wire.Str(tc.want) {
				t.Errorf("%s session error = %v, want %s", tc.conn.id, got, tc.want)
			}
		}
		if _, closed := bob.closeCode(); closed {
			t.Error("a refused reconnect closed the seat's connection")
		}
	})
}

func TestResync_WhenTheTurnSeatAsks_ShouldResendItsStateAndTellNobodyElse(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t, withTiming(noStartPause))
		waitID := intOf(t, lastDraw(t, alice), wire.KeyWaitID)
		bobBefore := len(bob.messages())

		sleep(4 * time.Second)
		h.m.Resync(alice)
		synctest.Wait()

		if got := intOf(t, reconnected(t, alice), wire.KeyWaitID); got != waitID {
			t.Errorf("game_reconnected wait id = %d, want the open decision %d", got, waitID)
		}
		opening := lastOpening(t, alice)
		if got, _ := opening.Get(wire.KeyWaitElapsed); got != wire.Float(4) || intOf(t, opening, wire.KeyWaitID) != waitID {
			t.Errorf("re-sent draw = %v, want wait %d after 4 s", opening, waitID)
		}
		if got := len(bob.messages()); got != bobBefore {
			t.Errorf("bob got %d messages from alice's resync, want none", got-bobBefore)
		}
		if _, closed := alice.closeCode(); closed || h.m.Stats().Resyncs != 1 {
			t.Errorf("resync closed = %v, Resyncs = %d, want an open connection and one resync",
				closed, h.m.Stats().Resyncs)
		}
	})
}

func TestResync_WhenTheGameIsPendingOrTheConnectionJoinedNone_ShouldAnswerWhy(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.join("Alice")
		stranger := h.connect()

		h.m.Resync(alice)
		h.m.Resync(stranger)
		synctest.Wait()

		for _, tc := range []struct {
			conn *fakeConn
			want messaging.SessionErrorCode
		}{
			{alice, messaging.SessionGameNotStarted},
			{stranger, messaging.SessionNotInGame},
		} {
			if got := sessionErrorCode(t, tc.conn); got != wire.Str(tc.want) {
				t.Errorf("%s session error = %v, want %s", tc.conn.id, got, tc.want)
			}
		}
	})
}
