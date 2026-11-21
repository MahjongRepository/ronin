package session

import (
	"context"
	"io"
	"log/slog"
	"path/filepath"
	"slices"
	"sync"
	"testing"
	"testing/synctest"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type recordingConn struct {
	id string

	mu     sync.Mutex
	events []wire.EventType
	code   CloseCode
	closed bool
}

func (c *recordingConn) ID() string     { return c.id }
func (c *recordingConn) GameID() string { return "game-audience" }

func (c *recordingConn) Send(data []byte) {
	m, err := wire.Decode(data)
	if err != nil {
		panic("the session sent an undecodable message: " + err.Error())
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if v, ok := m.Get(wire.KeyEventType); ok {
		if n, isInt := v.(wire.Int); isInt {
			c.events = append(c.events, wire.EventType(n))
		}
	}
}

func (c *recordingConn) Close(code CloseCode, _ string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.closed {
		c.closed, c.code = true, code
	}
}

func (c *recordingConn) closeCode() (CloseCode, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.code, c.closed
}

func (c *recordingConn) received(event wire.EventType) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return slices.Contains(c.events, event)
}

func TestSendEvents_WhenAnEventHasNoAudience_ShouldFailTheGameAndSendNothingOfIt(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		dir := t.TempDir()
		logger := slog.New(slog.NewTextHandler(io.Discard, nil))
		db, err := store.Open(t.Context(), filepath.Join(dir, "game.db"), logger)
		if err != nil {
			t.Fatalf("store.Open error = %v", err)
		}
		t.Cleanup(func() {
			closeErr := db.Close()
			if closeErr != nil {
				t.Errorf("db.Close error = %v", closeErr)
			}
		})
		m, err := New(context.Background(), Config{
			Timing: DefaultTiming(), Capacity: 1, DB: db,
			Replays: replayfile.New(filepath.Join(dir, "replays")), Logger: logger,
		})
		if err != nil {
			t.Fatalf("New error = %v", err)
		}
		err = m.CreatePendingGame("game-audience", []PlayerSpec{
			{Name: "Alice", UserID: "user-Alice", Ticket: "ticket-Alice"},
			{Name: "Bob", UserID: "user-Bob", Ticket: "ticket-Bob"},
		}, SeatingShuffled)
		if err != nil {
			t.Fatalf("CreatePendingGame error = %v", err)
		}
		alice, bob := &recordingConn{id: "conn-alice"}, &recordingConn{id: "conn-bob"}
		for _, joining := range []struct {
			conn   *recordingConn
			ticket string
		}{{alice, "ticket-Alice"}, {bob, "ticket-Bob"}} {
			m.Connect(joining.conn)
			m.Join(joining.conn, joining.ticket)
		}
		synctest.Wait()

		m.mu.Lock()
		g := m.games["game-audience"].game
		m.mu.Unlock()

		east := tile.Seats()[0]
		events := []play.Emitted{
			{To: play.ToAll(), Event: play.RiichiDeposited{Seat: east, Score: 24000, RiichiSticks: 1}},
			{Event: play.DoraRevealed{}},
		}
		g.postAndWait(func() {
			g.guard("send the test events", func() error { return g.sendEvents(events, nil, g.lazyTable()) })
		})
		synctest.Wait()

		for _, conn := range []*recordingConn{alice, bob} {
			if !conn.received(wire.EventRiichiDeclared) {
				t.Errorf("%s got no riichi declaration sent to all", conn.id)
			}
			if conn.received(wire.EventDoraRevealed) {
				t.Errorf("%s got the dora reveal sent to no seat", conn.id)
			}
			if code, closed := conn.closeCode(); !closed || code != CloseInternalError {
				t.Errorf("%s closed = %t with %d, want closed with %d", conn.id, closed, code, CloseInternalError)
			}
		}

		shutdownErr := m.Shutdown(context.Background())
		if shutdownErr != nil {
			t.Errorf("Shutdown error = %v", shutdownErr)
		}
	})
}
