package session_test

import (
	"encoding/json"
	"os"
	"testing"
	"testing/synctest"
	"time"

	"github.com/google/go-cmp/cmp"

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
