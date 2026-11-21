package session_test

import (
	"slices"
	"strings"
	"testing"
	"testing/synctest"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func twoHumans(t *testing.T, options ...option) (h *harness, alice, bob *fakeConn) {
	t.Helper()
	seed := seedSeating(t, 0, 1)
	h = newHarness(t, append([]option{withSeed(seed), withWalls(shuffledWall(seed, 0))}, options...)...)
	conns := h.start("Alice", "Bob")
	return h, conns[0], conns[1]
}

func TestSeatPlayers_WhenSeatingFixed_ShouldSeatThePlayersInWindOrderFromTheFirstDealer(t *testing.T) {
	seed, err := engine.ParseSeed(strings.Repeat("ee", engine.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	if dealer, _, _ := engine.FirstDealer(seed); dealer.Index() != 3 {
		t.Fatalf("seed's first dealer = %d, want 3", dealer.Index())
	}

	roster, seats := session.SeatPlayers("game-fixed", []string{"Alice", "Bob", "Charlie", "Dave"}, seed, session.SeatingFixed)

	seat := tile.Seats()
	if want := []tile.Seat{seat[3], seat[0], seat[1], seat[2]}; !slices.Equal(seats, want) {
		t.Errorf("SeatPlayers seats = %v, want %v", seats, want)
	}
	if want := [tile.SeatCount]string{"Bob", "Charlie", "Dave", "Alice"}; roster.Names != want || roster.AI != [tile.SeatCount]bool{} {
		t.Errorf("SeatPlayers roster = %v %v, want %v and no AI seat", roster.Names, roster.AI, want)
	}
}

func TestJoin_WhenTheLastPlayerJoins_ShouldSendTheStartAndTheDealOpeningTheStartConfirmation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		_, alice, bob := twoHumans(t)

		for _, tc := range []struct {
			conn *fakeConn
			seat int
		}{{alice, 0}, {bob, 1}} {
			messages := tc.conn.messages()
			started := ofEvent(messages, wire.EventGameStarted)
			if len(started) != 1 || intOf(t, started[0], wire.KeySeat) != tc.seat {
				t.Fatalf("%s game_started = %v, want one naming seat %d", tc.conn.id, started, tc.seat)
			}
			if _, ok := started[0].Get(wire.KeyTimerSettings); !ok {
				t.Errorf("%s game_started carries no timer settings", tc.conn.id)
			}

			dealt := ofEvent(messages, wire.EventRoundStarted)
			if len(dealt) != 1 {
				t.Fatalf("%s got %d deals, want 1", tc.conn.id, len(dealt))
			}
			if got := intOf(t, dealt[0], wire.KeyWaitID); got != 1 {
				t.Errorf("%s deal wait id = %d, want 1", tc.conn.id, got)
			}
			if got, _ := dealt[0].Get(wire.KeyRoundAdvanceSeconds); got != wire.Int(10) {
				t.Errorf("%s deal pause timeout = %v, want whole 10", tc.conn.id, got)
			}
			if draws := ofEvent(messages, wire.EventDraw); len(draws) != 0 {
				t.Errorf("%s got a draw before the start was confirmed", tc.conn.id)
			}
		}
	})
}

func TestGameStartConfirm_WhenEveryPlayerConfirms_ShouldSendTheDealersDrawAtOnce(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t)

		h.confirm(alice)
		if got := len(ofEvent(alice.messages(), wire.EventDraw)); got != 0 {
			t.Fatalf("the dealer drew with %d draws before every seat confirmed", got)
		}
		h.confirm(bob)

		draws := ofEvent(alice.messages(), wire.EventDraw)
		if len(draws) != 1 {
			t.Fatalf("the dealer got %d draws, want 1", len(draws))
		}
		if got := intOf(t, draws[0], wire.KeyWaitID); got != 2 {
			t.Errorf("draw wait id = %d, want 2", got)
		}
		if got, _ := draws[0].Get(wire.KeyBankSeconds); got != wire.Int(20) {
			t.Errorf("draw bank = %v, want whole 20", got)
		}
		if got := len(ofEvent(bob.messages(), wire.EventDrawNotice)); got != 1 {
			t.Errorf("bob got %d draw notices, want 1", got)
		}
	})
}

func TestGameStartConfirm_WhenItsTimeoutFires_ShouldConfirmForTheSeatsLeftAndDraw(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, _ := twoHumans(t)
		h.confirm(alice)

		sleep(10*time.Second - time.Millisecond)
		if got := len(ofEvent(alice.messages(), wire.EventDraw)); got != 0 {
			t.Fatalf("the dealer drew before the confirmation timed out")
		}
		sleep(time.Millisecond)

		if got := len(ofEvent(alice.messages(), wire.EventDraw)); got != 1 {
			t.Errorf("the dealer got %d draws after the timeout, want 1", got)
		}
		if got := h.m.Stats().RoundAdvanceTimeouts; got != 1 {
			t.Errorf("RoundAdvanceTimeouts = %d, want 1", got)
		}
	})
}

func TestGameStartConfirm_WhenItsTimeoutIsZero_ShouldDrawRightAfterTheDeal(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		_, alice, _ := twoHumans(t, withTiming(func(timing *session.Timing) { timing.GameStartConfirm = 0 }))

		messages := alice.messages()
		dealt := ofEvent(messages, wire.EventRoundStarted)
		if _, stamped := dealt[0].Get(wire.KeyWaitID); stamped {
			t.Error("the deal opens a confirmation with no start pause")
		}
		draws := ofEvent(messages, wire.EventDraw)
		if len(draws) != 1 || intOf(t, draws[0], wire.KeyWaitID) != 1 {
			t.Errorf("draws = %v, want one opening wait 1", draws)
		}
	})
}

func TestConfirmRound_WhenTheSeatConfirmedOrEchoesAnOldID_ShouldAnswerStaleAction(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t)

		h.confirm(alice)
		h.confirm(alice)
		h.act(bob, confirmRound(0))

		for _, tc := range []struct {
			conn   *fakeConn
			waitID int
		}{{alice, 1}, {bob, 0}} {
			errs := ofEvent(tc.conn.messages(), wire.EventError)
			if len(errs) != 1 {
				t.Fatalf("%s got %d errors, want 1", tc.conn.id, len(errs))
			}
			if got, _ := errs[0].Get(wire.KeyGameErrorCode); got != wire.Str("stale_action") {
				t.Errorf("%s error code = %v, want stale_action", tc.conn.id, got)
			}
			if got := intOf(t, errs[0], wire.KeyWaitID); got != tc.waitID {
				t.Errorf("%s error wait id = %d, want %d", tc.conn.id, got, tc.waitID)
			}
		}
		if got := len(ofEvent(alice.messages(), wire.EventDraw)); got != 0 {
			t.Error("a stale confirmation ended the start pause")
		}
	})
}

func confirmRound(waitID int) messaging.GameActionMessage {
	return messaging.GameActionMessage{Action: messaging.GameActionConfirmRound, WaitID: waitID}
}

func TestJoin_WhenAnActionFollowsOnTheSameConnection_ShouldReturnOnlyOnceTheBindRan(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.connectHeld()

		joined := make(chan struct{})
		go func() {
			h.m.Join(alice, "ticket-Alice")
			close(joined)
		}()
		synctest.Wait()
		select {
		case <-joined:
			t.Error("Join returned while its step was still sending game_joined")
		default:
		}

		close(alice.release)
		<-joined
		h.m.Act(alice, messaging.GameActionMessage{Action: messaging.GameActionConfirmRound})
		synctest.Wait()

		errs := ofSession(alice.messages(), "session_error")
		if len(errs) != 1 {
			t.Fatalf("Alice got %d session errors, want 1", len(errs))
		}
		if got, _ := errs[0].Get(wire.KeySessionErrorCode); got != wire.Str(messaging.SessionGameNotStarted) {
			t.Errorf("Alice's pipelined action was answered %v, want %s", got, messaging.SessionGameNotStarted)
		}
	})
}

func TestQueueDelayMax_WhenAJoinWaitsBehindABusyStep_ShouldReportHowLongItWaited(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.connectHeld()
		go h.m.Join(alice, "ticket-Alice")
		sleep(500 * time.Millisecond)
		bob := h.connect()
		go h.m.Join(bob, "ticket-Bob")

		sleep(1000 * time.Millisecond)
		close(alice.release)
		synctest.Wait()

		got, seen := h.m.QueueDelayMax()
		if !seen || got != 1000 {
			t.Errorf("QueueDelayMax() = %v, %t, want 1000, true", got, seen)
		}
	})
}
