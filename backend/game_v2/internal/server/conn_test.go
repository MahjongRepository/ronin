package server

import (
	"bytes"
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"

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

type lockedLog struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (l *lockedLog) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.buf.Write(p)
}

func (l *lockedLog) String() string {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.buf.String()
}

func TestConnectionWrite_WhenThePeerStopsReading_ShouldDropItPastTheSendDeadline(t *testing.T) {
	logs := &lockedLog{}
	s := &Server{log: slog.New(slog.NewTextHandler(logs, nil)), stats: socketStats{closes: initialCloses()}}
	s.cfg.Socket.SendDeadline = 50 * time.Millisecond
	accepted := make(chan *connection, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ws, err := websocket.Accept(w, r, nil)
		if err != nil {
			t.Errorf("accept: %v", err)
			return
		}

		conn := newConnection(ws, "game-0001", s)
		accepted <- conn
		conn.write(context.Background())
	}))
	defer srv.Close()
	peer, upgrade, err := websocket.Dial(t.Context(), srv.URL, nil)
	if upgrade != nil && upgrade.Body != nil {
		_ = upgrade.Body.Close()
	}
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	defer func() { _ = peer.CloseNow() }()
	conn := <-accepted

	chunk := make([]byte, 1<<20)
	for range 64 {
		conn.Send(chunk)
	}

	select {
	case <-conn.writerDone:
	case <-time.After(5 * time.Second):
		t.Fatal("the writer kept a peer that stopped reading")
	}
	if !strings.Contains(logs.String(), logSendDeadline) {
		t.Errorf("logs = %q, want the send deadline", logs.String())
	}
}

func TestConnectionSendDeadline_WhenTheTimerObservedAnEarlierWrite_ShouldKeepTheNextOne(t *testing.T) {
	c := &connection{terminated: make(chan struct{}), sendDeadline: time.Hour, sendEpoch: time.Now()}
	c.terminate = sync.OnceFunc(func() { close(c.terminated) })
	defer c.disarmSendDeadline()

	c.armSendDeadline()
	observedEarlierDue := c.sendDue.Load()
	c.disarmSendDeadline()
	c.armSendDeadline()
	c.dropIfObservedSendOverdue(observedEarlierDue, time.Duration(observedEarlierDue))

	if c.isTerminated() || c.sendTimedOut.Load() {
		t.Error("a timer firing for an earlier write dropped the write in flight")
	}
}
