package session_test

import (
	"errors"
	"testing"
	"testing/synctest"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func TestCreatePendingGame_WhenItCannotRegister_ShouldRefuseWithItsReason(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t, func(c *session.Config) { c.Capacity = 2 })
		h.create("Alice")

		cases := []struct {
			name    string
			gameID  string
			players []session.PlayerSpec
			want    error
		}{
			{name: "taken id", gameID: testGameID, players: specs("Bob"), want: session.ErrGameExists},
			{name: "player already playing", gameID: "game-0002", players: specs("Alice"), want: session.ErrPlayerPlaying},
			{name: "no player", gameID: "game-0002", players: nil, want: session.ErrPlayerCount},
			{name: "five players", gameID: "game-0002", players: specs("A", "B", "C", "D", "E"), want: session.ErrPlayerCount},
		}
		for _, tc := range cases {
			err := h.m.CreatePendingGame(tc.gameID, tc.players, session.SeatingShuffled)
			if !errors.Is(err, tc.want) {
				t.Errorf("%s: CreatePendingGame error = %v, want %v", tc.name, err, tc.want)
			}
		}

		err := h.m.CreatePendingGame("game-0002", specs("Bob"), session.SeatingShuffled)
		if err != nil {
			t.Fatalf("CreatePendingGame error = %v", err)
		}

		err = h.m.CreatePendingGame("game-0003", specs("Carol"), session.SeatingShuffled)
		if !errors.Is(err, session.ErrAtCapacity) {
			t.Errorf("CreatePendingGame at capacity error = %v, want ErrAtCapacity", err)
		}
	})
}

func TestWithdrawGame_WhenNobodyJoined_ShouldAbandonItAndRefuseItsIDAfterwards(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice")

		if !h.m.WithdrawGame(testGameID) {
			t.Fatal("WithdrawGame = false, want true")
		}

		synctest.Wait()
		if _, playing := h.m.PlayingGame("user-Alice"); playing {
			t.Error("Alice still plays the withdrawn game")
		}

		err := h.m.CreatePendingGame(testGameID, specs("Alice"), session.SeatingShuffled)
		if !errors.Is(err, session.ErrGameWithdrawn) {
			t.Errorf("CreatePendingGame after withdrawal error = %v, want ErrGameWithdrawn", err)
		}
		if h.hasPlayedGame(t) {
			t.Error("a withdrawn pending game wrote a played_games row")
		}
	})
}

func TestWithdrawGame_WhenItsCreationArrivesLater_ShouldRefuseTheCreationForADay(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)

		if !h.m.WithdrawGame(testGameID) {
			t.Fatal("WithdrawGame of an unknown game = false, want true")
		}

		err := h.m.CreatePendingGame(testGameID, specs("Alice"), session.SeatingShuffled)
		if !errors.Is(err, session.ErrGameWithdrawn) {
			t.Errorf("CreatePendingGame error = %v, want ErrGameWithdrawn", err)
		}

		sleep(24 * time.Hour)
		err = h.m.CreatePendingGame(testGameID, specs("Alice"), session.SeatingShuffled)
		if err != nil {
			t.Errorf("CreatePendingGame a day later error = %v", err)
		}
	})
}

func TestWithdrawGame_WhenAPlayerJoined_ShouldKeepTheGame(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		h.join("Alice")

		if h.m.WithdrawGame(testGameID) {
			t.Error("WithdrawGame = true, want false")
		}
		if got := h.m.GameCounts(); got != (session.GameCounts{Pending: 1}) {
			t.Errorf("GameCounts = %+v, want one pending game", got)
		}
	})
}

func TestPendingGameTimeout_WhenNobodyConnected_ShouldAbandonTheGameWithNoRecord(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice")

		sleep(session.DefaultTiming().PendingGame)
		if got := h.m.GameCounts(); got != (session.GameCounts{}) {
			t.Errorf("GameCounts = %+v, want none", got)
		}
		if _, playing := h.m.PlayingGame("user-Alice"); playing {
			t.Error("Alice still plays the abandoned game")
		}
		if h.hasPlayedGame(t) {
			t.Error("an abandoned pending game wrote a played_games row")
		}
	})
}

func TestPendingGameTimeout_WhenOnePlayerConnected_ShouldStartWithAnAIPlayerInTheAbsentSeat(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t, withSeed(seedSeating(t, 0, 1)))
		h.create("Alice", "Bob")
		alice := h.join("Alice")

		sleep(session.DefaultTiming().PendingGame)

		control := ofSession(alice.messages(), "seat_control")
		want := []wire.Map{{
			{Key: wire.KeySessionType, Value: wire.Str("seat_control")},
			{Key: wire.KeySeat, Value: wire.Int(1)},
			{Key: wire.KeySeatControlReason, Value: wire.Int(wire.SeatControlAbsent)},
		}}
		if diff := cmp.Diff(want, control); diff != "" {
			t.Errorf("seat_control messages differ (-want +got):\n%s", diff)
		}
		if got := h.m.GameCounts(); got != (session.GameCounts{Playing: 1}) {
			t.Errorf("GameCounts = %+v, want one playing game", got)
		}
	})
}

func TestJoin_WhenItCannotBind_ShouldAnswerWhy(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.join("Alice")

		h.m.Join(alice, "ticket-Bob", noClaim)
		stranger := h.connect()
		h.m.Join(stranger, "ticket-Nobody", noClaim)
		lost := &fakeConn{id: "conn-lost", gameID: "game-0404"}
		h.m.Connect(lost)
		h.m.Join(lost, "ticket-Alice", noClaim)
		synctest.Wait()

		for _, tc := range []struct {
			conn *fakeConn
			want messaging.SessionErrorCode
		}{
			{conn: alice, want: messaging.SessionAlreadyInGame},
			{conn: stranger, want: messaging.SessionJoinGameNoSession},
			{conn: lost, want: messaging.SessionJoinGameNotFound},
		} {
			errs := ofSession(tc.conn.messages(), "session_error")
			if len(errs) != 1 {
				t.Errorf("%s got %d session errors, want 1", tc.conn.id, len(errs))
				continue
			}
			if got, _ := errs[0].Get(wire.KeySessionErrorCode); got != wire.Str(tc.want) {
				t.Errorf("%s session error = %v, want %s", tc.conn.id, got, tc.want)
			}
		}
	})
}

func TestJoin_WhenTheTicketIsReusedByANewConnection_ShouldCloseTheOldWith4002(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		first := h.join("Alice")
		second := h.join("Alice")

		if code, closed := first.closeCode(); !closed || code != session.CloseReplaced {
			t.Errorf("first connection close = %v, %v, want 4002", code, closed)
		}
		if got := len(ofSession(second.messages(), "game_joined")); got != 1 {
			t.Errorf("second connection got %d game_joined, want 1", got)
		}
		if got := h.m.Stats().Takeovers; got != 1 {
			t.Errorf("Takeovers = %d, want 1", got)
		}
	})
}

func TestAuthTimeout_WhenAConnectionNeverAuthenticates_ShouldCloseIt4001(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		idle := h.connect()
		joined := h.join("Alice")

		sleep(10 * time.Second)
		if code, closed := idle.closeCode(); !closed || code != session.CloseAuthTimeout {
			t.Errorf("idle connection close = %v, %v, want 4001", code, closed)
		}
		if _, closed := joined.closeCode(); closed {
			t.Error("the joined connection was closed")
		}

		h.m.Join(idle, "ticket-Bob", noClaim)
		synctest.Wait()
		if got := len(idle.messages()); got != 0 {
			t.Errorf("the evicted connection got %d messages, want none", got)
		}
	})
}

func TestGameAction_WhenTheGameIsPendingOrTheConnectionJoinedNone_ShouldAnswerWhy(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.join("Alice")
		stranger := h.connect()

		confirm := messaging.GameActionMessage{Action: messaging.GameActionConfirmRound}
		h.act(alice, confirm)
		h.act(stranger, confirm)

		for _, tc := range []struct {
			conn *fakeConn
			want messaging.SessionErrorCode
		}{
			{conn: alice, want: messaging.SessionGameNotStarted},
			{conn: stranger, want: messaging.SessionNotInGame},
		} {
			errs := ofSession(tc.conn.messages(), "session_error")
			if len(errs) != 1 {
				t.Errorf("%s got %d session errors, want 1", tc.conn.id, len(errs))
				continue
			}
			if got, _ := errs[0].Get(wire.KeySessionErrorCode); got != wire.Str(tc.want) {
				t.Errorf("%s session error = %v, want %s", tc.conn.id, got, tc.want)
			}
		}
	})
}
