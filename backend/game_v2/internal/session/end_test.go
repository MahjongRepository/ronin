package session_test

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"testing/synctest"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func playOneWallGame(t *testing.T, h *harness) *fakeConn {
	t.Helper()
	h.create("Alice", "Bob")
	alice := h.join("Alice")
	sleep(session.DefaultTiming().PendingGame)
	sleep(3 * time.Hour)
	return alice
}

func oneWallHarness(t *testing.T) *harness {
	t.Helper()
	seed := seedSeating(t, 0, 1)
	return newHarness(t, withSeed(seed), withWalls(shuffledWall(seed, 0)))
}

func TestGameEnd_WhenTheLastWallIsDealt_ShouldSaveTheReplayRecordTheFinishAndClose1000(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := oneWallHarness(t)
		alice := playOneWallGame(t, h)

		if code, closed := alice.closeCode(); !closed || code != session.CloseGameEnded {
			t.Fatalf("alice close = %v, %v, want 1000", code, closed)
		}
		if got := len(ofEvent(alice.messages(), wire.EventGameEnd)); got != 1 {
			t.Errorf("alice got %d game ends, want 1", got)
		}
		if got := h.m.GameCounts(); got != (session.GameCounts{}) {
			t.Errorf("GameCounts = %+v, want none", got)
		}

		reason, data := h.playedGame(t)
		if reason.String != "completed" {
			t.Errorf("end_reason = %q, want completed", reason.String)
		}
		var row struct {
			Rounds    int `json:"num_rounds_played"`
			Standings []struct {
				Seat   int    `json:"seat"`
				UserID string `json:"user_id"`
				Score  *int   `json:"score"`
			} `json:"standings"`
		}
		err := json.Unmarshal([]byte(data), &row)
		if err != nil {
			t.Fatalf("data %s: %v", data, err)
		}
		if row.Rounds != 1 || len(row.Standings) != 4 || row.Standings[0].Score == nil {
			t.Errorf("data = %s, want one round and four scored standings", data)
		}

		var kinds []wire.EventType
		for _, record := range h.replay(t)[1:5] {
			typ, _ := eventType(record)
			kinds = append(kinds, typ)
		}
		want := []wire.EventType{wire.EventGameStarted, wire.EventRoundStarted, wire.EventSeatControl, wire.EventDraw}
		if diff := cmp.Diff(want, kinds); diff != "" {
			t.Errorf("replay start differs (-want +got):\n%s", diff)
		}
	})
}

func TestGameEnd_WhenTheReplayCannotBeSaved_ShouldEndAsAFailureAndClose1011(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := oneWallHarness(t)
		h.allowErrs = true
		err := os.WriteFile(h.replayDir, nil, 0o600)
		if err != nil {
			t.Fatal(err)
		}

		alice := playOneWallGame(t, h)

		if code, closed := alice.closeCode(); !closed || code != session.CloseInternalError {
			t.Errorf("alice close = %v, %v, want 1011", code, closed)
		}
		if got := len(ofSession(alice.messages(), "session_error")); got != 1 {
			t.Errorf("alice got %d session errors, want the internal error", got)
		}
		if reason, _ := h.playedGame(t); reason.String != "error" {
			t.Errorf("end_reason = %q, want error", reason.String)
		}
	})
}

func assertClosedWithInternalError(t *testing.T, conn *fakeConn) {
	t.Helper()
	if code, closed := conn.closeCode(); !closed || code != session.CloseInternalError {
		t.Errorf("%s close = %v, %v, want 1011", conn.id, code, closed)
	}
}

func TestGameFailure_WhenASendPanicsMidGameAndAgainInTheFinalizer_ShouldEndOnceAsAnError(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, bob := twoHumans(t, withTiming(noStartPause))
		h.allowErrs = true
		draw := lastDraw(t, alice)
		bob.breakSends(100)

		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))

		assertClosedWithInternalError(t, alice)
		assertClosedWithInternalError(t, bob)
		if got := sessionErrorCode(t, alice); got != wire.Str(messaging.SessionInternalError) {
			t.Errorf("alice session error = %v, want internal_error", got)
		}
		logs := h.logs.String()
		if got := strings.Count(logs, "game failed"); got != 1 {
			t.Errorf("logged %d game failures, want 1", got)
		}
		if !strings.Contains(logs, "close a connection of an ended game") {
			t.Error("the finalizer's close met no fault")
		}
		if reason, _ := h.playedGame(t); reason.String != "error" {
			t.Errorf("end_reason = %q, want error", reason.String)
		}
		if got := len(h.replay(t)); got == 0 {
			t.Error("the failed game saved an empty replay")
		}
		if got := h.m.GameCounts(); got != (session.GameCounts{}) {
			t.Errorf("GameCounts = %+v, want none", got)
		}
	})
}

func TestJoin_WhenServingAnUnseatedConnectionPanics_ShouldFailTheGameAndCloseTheConnection1011(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice, _ := twoHumans(t)
		h.allowErrs = true
		late := h.connect()
		late.breakSends(1)

		h.m.Join(late, "ticket-Alice")
		synctest.Wait()

		assertClosedWithInternalError(t, late)
		if got := sessionErrorCode(t, late); got != wire.Str(messaging.SessionInternalError) {
			t.Errorf("late connection session error = %v, want internal_error", got)
		}
		assertClosedWithInternalError(t, alice)
		if reason, _ := h.playedGame(t); reason.String != "error" {
			t.Errorf("end_reason = %q, want error", reason.String)
		}
	})
}

func TestGameStart_WhenTheEngineGameCannotStart_ShouldFailTheGameWithNoRecord(t *testing.T) {
	for _, tc := range []struct {
		name  string
		setup func(engine.Seed) engine.Setup
		start func(h *harness) *fakeConn
	}{
		{
			name:  "setup panics on the pending timeout",
			setup: func(engine.Seed) engine.Setup { panic("no setup") },
			start: func(h *harness) *fakeConn {
				h.create("Alice", "Bob")
				alice := h.join("Alice")
				sleep(session.DefaultTiming().PendingGame)
				return alice
			},
		},
		{
			name:  "no wall at the last join",
			setup: func(engine.Seed) engine.Setup { return engine.Setup{Walls: play.Fixed{}} },
			start: func(h *harness) *fakeConn { return h.start("Alice")[0] },
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			synctest.Test(t, func(t *testing.T) {
				h := newHarness(t, func(c *session.Config) { c.Setup = tc.setup })
				h.allowErrs = true

				alice := tc.start(h)

				assertClosedWithInternalError(t, alice)
				if h.hasPlayedGame(t) {
					t.Error("a game that never started wrote a played_games row")
				}
				if _, playing := h.m.PlayingGame("user-Alice"); playing {
					t.Error("Alice still plays the failed game")
				}
			})
		})
	}
}

func TestShutdown_WhenAGameIsStillPending_ShouldEndItUnrecordedAndRefuseNewGames(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := newHarness(t)
		h.create("Alice", "Bob")
		alice := h.join("Alice")
		idle := h.connect()

		err := h.m.Shutdown(context.Background())
		if err != nil {
			t.Fatalf("Shutdown error = %v", err)
		}
		sleep(time.Hour)

		if _, closed := idle.closeCode(); closed {
			t.Error("the unauthenticated connection was closed after Shutdown")
		}
		if _, closed := alice.closeCode(); closed {
			t.Error("Shutdown closed the pending game's connection")
		}
		if h.hasPlayedGame(t) {
			t.Error("the vanished pending game wrote a played_games row")
		}
		err = h.m.CreatePendingGame("game-0002", specs("Carol"))
		if !errors.Is(err, session.ErrShuttingDown) {
			t.Errorf("CreatePendingGame after Shutdown error = %v, want ErrShuttingDown", err)
		}
	})
}
