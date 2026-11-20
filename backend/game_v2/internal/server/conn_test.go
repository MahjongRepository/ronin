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

	accepted := []byte("accepted")
	c.Send(accepted)
	c.Close(session.CloseGameEnded, "")
	c.Send([]byte("late"))
	c.Close(session.CloseGameEnded, "")

	if got := stats.messagesOut.Load(); got != 1 {
		t.Errorf("messages out = %d, want 1", got)
	}
	if got, want := stats.bytesOut.Load(), int64(len(accepted)); got != want {
		t.Errorf("bytes out = %d, want %d", got, want)
	}
	if got := stats.closes[int(session.CloseGameEnded)]; got != 1 {
		t.Errorf("closes = %d, want 1", got)
	}
}
