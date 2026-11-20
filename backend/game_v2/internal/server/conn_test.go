package server

import (
	"log/slog"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
)

func TestConnectionSend_WhenConnectionClosed_ShouldCountNothingDropped(t *testing.T) {
	stats := socketStats{closes: initialCloses()}
	c := &connection{
		stats:      &stats,
		log:        slog.New(slog.DiscardHandler),
		queue:      make(chan outgoing, sendQueueLimit),
		terminated: make(chan struct{}),
	}

	c.Close(session.CloseGameEnded, "")
	c.Send([]byte("late"))
	c.Close(session.CloseGameEnded, "")

	if got := stats.messagesOut.Load(); got != 0 {
		t.Errorf("messages out = %d, want 0", got)
	}
	if got := stats.bytesOut.Load(); got != 0 {
		t.Errorf("bytes out = %d, want 0", got)
	}
	if got := stats.closes[int(session.CloseGameEnded)]; got != 1 {
		t.Errorf("closes = %d, want 1", got)
	}
}
