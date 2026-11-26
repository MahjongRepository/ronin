package session_test

import (
	"testing"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type stoppedClock struct{}

func (stoppedClock) Now() time.Time {
	return time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
}

func (stoppedClock) AfterFunc(time.Duration, func()) func() bool {
	return func() bool { return true }
}

func withStoppedClock() option {
	return func(c *session.Config) { c.Clock = stoppedClock{} }
}

func TestSettle_WhenTheLastJoinStartsTheGame_ShouldReturnOnceTheDealWasSent(t *testing.T) {
	h := newHarness(t, withStoppedClock())
	h.create("Alice")
	conn := h.connect()

	h.m.Join(conn, "ticket-Alice", noClaim)
	h.m.Settle()
	if got := ofEvent(conn.messages(), wire.EventRoundStarted); len(got) != 1 {
		t.Errorf("round starts sent before Settle returned = %d, want 1", len(got))
	}
}

func TestSettle_WhenTheLastParticipantLeaves_ShouldReturnOnceTheFinalizerRecordedTheEnd(t *testing.T) {
	h := newHarness(t, withStoppedClock())
	h.create("Alice")
	conn := h.connect()
	h.m.Join(conn, "ticket-Alice", noClaim)
	h.m.Settle()

	h.m.Disconnect(conn)
	h.m.Settle()
	if reason, _ := h.playedGame(t); reason.String != "abandoned" {
		t.Errorf("end reason recorded before Settle returned = %q, want abandoned", reason.String)
	}
}
