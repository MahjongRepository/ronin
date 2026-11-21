package session_test

import (
	"testing"
	"testing/synctest"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const testObserveDelay = time.Minute

func withObserveDelay(d time.Duration) option {
	return func(c *session.Config) { c.ObserveDelay = d }
}

func (h *harness) observe(t *testing.T, from int) session.Observation {
	t.Helper()
	got, found := h.m.Observe(testGameID, from)
	if !found {
		t.Fatalf("Observe(%d) found no game", from)
	}
	return got
}

func eventTypes(records []wire.Map) []wire.EventType {
	kinds := make([]wire.EventType, 0, len(records))
	for _, record := range records {
		typ, _ := eventType(record)
		kinds = append(kinds, typ)
	}
	return kinds
}

func TestObserve_WhenTheDelayPasses_ShouldServeOnlyRecordsOlderThanIt(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h, alice := soloDealer(t, withTiming(noWaits), withObserveDelay(testObserveDelay))
		before := h.observe(t, 0)
		if len(before.Records) != 0 || before.Next != 0 || before.Ended || before.AvailableIn != testObserveDelay {
			t.Fatalf("Observe at the start = %d records, next %d, ended %v, available in %v, want none for the delay",
				len(before.Records), before.Next, before.Ended, before.AvailableIn)
		}

		sleep(5 * time.Second)
		draw := lastDraw(t, alice)
		h.act(alice, discard(intOf(t, draw, wire.KeyWaitID), drawnTile(t, draw)))
		sleep(testObserveDelay - 5*time.Second)

		started := h.observe(t, 0)
		wantStart := []wire.EventType{wire.EventGameStarted, wire.EventRoundStarted, wire.EventDraw}
		if diff := cmp.Diff(wantStart, eventTypes(started.Records)); diff != "" {
			t.Fatalf("records once the start is old enough differ (-want +got):\n%s", diff)
		}
		if started.Next != len(wantStart) || started.Ended || started.AvailableIn != 0 {
			t.Errorf("Observe after the delay = next %d, ended %v, available in %v, want next 3, not ended, now",
				started.Next, started.Ended, started.AvailableIn)
		}
		if _, seeded := started.Records[0].Get(wire.KeySeed); seeded {
			t.Errorf("the observed game start holds the seed")
		}

		sleep(5 * time.Second)
		turn := h.observe(t, started.Next)
		wantTurn := []wire.EventType{wire.EventDiscard}
		for range 3 {
			wantTurn = append(wantTurn, wire.EventDraw, wire.EventDiscard)
		}
		if diff := cmp.Diff(wantTurn, eventTypes(turn.Records)); diff != "" {
			t.Errorf("records of alice's discard up to the one she may chi, her chi timeout left out, "+
				"differ (-want +got):\n%s", diff)
		}
		if turn.Next != started.Next+len(wantTurn) || turn.Ended {
			t.Errorf("Observe of alice's turn = next %d, ended %v, want next %d, not ended",
				turn.Next, turn.Ended, started.Next+len(wantTurn))
		}

		beyond := h.observe(t, turn.Next+10)
		if len(beyond.Records) != 0 || beyond.Next != turn.Next+10 {
			t.Errorf("Observe past the eligible records = %d records, next %d, want none and next %d",
				len(beyond.Records), beyond.Next, turn.Next+10)
		}
	})
}

func TestObserve_WhenTheGameEnds_ShouldServeItToTheEndOnceTheEndIsOldEnoughThenExpire(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		h := oneWallHarness(t, withObserveDelay(testObserveDelay))
		h.create("Alice", "Bob")
		alice := h.join("Alice")
		for range 3 * 60 * 60 {
			if _, closed := alice.closeCode(); closed {
				break
			}
			sleep(time.Second)
		}
		if _, closed := alice.closeCode(); !closed {
			t.Fatalf("the game did not end within 3 hours")
		}

		ending := h.observe(t, 0)
		if ending.Ended || len(ending.Records) == 0 {
			t.Errorf("Observe right after the end = %d records, ended %v, want the older records, not ended",
				len(ending.Records), ending.Ended)
		}

		sleep(testObserveDelay)
		ended := h.observe(t, 0)
		saved := len(h.replay(t)) - 1
		if !ended.Ended || len(ended.Records) != saved || ended.Next != saved {
			t.Errorf("Observe once the end is old enough = %d records, next %d, ended %v, want all %d and ended",
				len(ended.Records), ended.Next, ended.Ended, saved)
		}

		sleep(time.Minute)
		if _, found := h.m.Observe(testGameID, 0); found {
			t.Errorf("Observe past the retention found the game")
		}
	})
}
