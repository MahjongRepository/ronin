package session_test

import (
	"bytes"
	"compress/gzip"
	"context"
	"database/sql"
	"io"
	"log/slog"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const testGameID = "game-0001"

type fakeConn struct {
	id     string
	gameID string

	mu     sync.Mutex
	sent   []wire.Map
	closed bool
	code   session.CloseCode
	reason string
}

func (c *fakeConn) ID() string     { return c.id }
func (c *fakeConn) GameID() string { return c.gameID }

func (c *fakeConn) Send(data []byte) {
	m, err := wire.Decode(data)
	if err != nil {
		panic("the session sent an undecodable message: " + err.Error())
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.closed {
		c.sent = append(c.sent, m)
	}
}

func (c *fakeConn) Close(code session.CloseCode, reason string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.closed {
		c.closed, c.code, c.reason = true, code, reason
	}
}

func (c *fakeConn) messages() []wire.Map {
	c.mu.Lock()
	defer c.mu.Unlock()
	return slices.Clone(c.sent)
}

func (c *fakeConn) closeCode() (session.CloseCode, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.code, c.closed
}

type lockedBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *lockedBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *lockedBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

type harness struct {
	t         *testing.T
	m         *session.Manager
	dbPath    string
	replayDir string
	logs      *lockedBuffer
	allowErrs bool
	nextConn  int
}

type option func(*session.Config)

func withTiming(edit func(*session.Timing)) option {
	return func(c *session.Config) { edit(&c.Timing) }
}

func withSeed(seed engine.Seed) option {
	return func(c *session.Config) { c.Seeds = func() engine.Seed { return seed } }
}

func withWalls(walls ...[tile.TileIDCount]tile.TileID) option {
	return func(c *session.Config) {
		c.Setup = func(engine.Seed) engine.Setup { return engine.Setup{Walls: play.Fixed{Walls: walls}} }
	}
}

func newHarness(t *testing.T, options ...option) *harness {
	t.Helper()
	dir := t.TempDir()
	logs := &lockedBuffer{}
	logger := slog.New(slog.NewTextHandler(logs, &slog.HandlerOptions{Level: slog.LevelDebug}))
	db, err := store.Open(t.Context(), filepath.Join(dir, "game.db"), logger)
	if err != nil {
		t.Fatalf("store.Open error = %v", err)
	}

	cfg := session.Config{
		Timing:   session.DefaultTiming(),
		Capacity: 10,
		DB:       db,
		Replays:  store.NewReplays(filepath.Join(dir, "replays")),
		Logger:   logger,
	}
	for _, apply := range options {
		apply(&cfg)
	}
	m, err := session.New(context.Background(), cfg)
	if err != nil {
		t.Fatalf("session.New error = %v", err)
	}

	h := &harness{
		t: t, m: m, dbPath: filepath.Join(dir, "game.db"), replayDir: filepath.Join(dir, "replays"), logs: logs,
	}
	t.Cleanup(func() {
		shutdownErr := m.Shutdown(context.Background())
		if shutdownErr != nil {
			t.Errorf("Shutdown error = %v", shutdownErr)
		}
		closeErr := db.Close()
		if closeErr != nil {
			t.Errorf("db.Close error = %v", closeErr)
		}
		if !h.allowErrs && strings.Contains(logs.String(), "level=ERROR") {
			t.Errorf("the session logged an error:\n%s", logs.String())
		}
	})
	return h
}

func specs(names ...string) []session.PlayerSpec {
	players := make([]session.PlayerSpec, 0, len(names))
	for _, name := range names {
		players = append(players, session.PlayerSpec{Name: name, UserID: "user-" + name, Ticket: "ticket-" + name})
	}
	return players
}

func (h *harness) create(names ...string) {
	h.t.Helper()
	err := h.m.CreatePendingGame(testGameID, specs(names...))
	if err != nil {
		h.t.Fatalf("CreatePendingGame error = %v", err)
	}
}

func (h *harness) connect() *fakeConn {
	h.nextConn++
	conn := &fakeConn{id: "conn-" + strconv.Itoa(h.nextConn), gameID: testGameID}
	h.m.Connect(conn)
	return conn
}

func (h *harness) join(name string) *fakeConn {
	conn := h.connect()
	h.m.Join(conn, "ticket-"+name)
	synctest.Wait()
	return conn
}

func (h *harness) start(names ...string) []*fakeConn {
	h.create(names...)
	conns := make([]*fakeConn, 0, len(names))
	for _, name := range names {
		conns = append(conns, h.join(name))
	}
	return conns
}

func (h *harness) act(conn *fakeConn, message messaging.GameActionMessage) {
	h.m.Act(conn, message)
	synctest.Wait()
}

func (h *harness) confirm(conn *fakeConn) {
	h.act(conn, messaging.GameActionMessage{Action: messaging.GameActionConfirmRound, WaitID: lastWaitID(h.t, conn)})
}

func sleep(d time.Duration) {
	time.Sleep(d)
	synctest.Wait()
}

func (h *harness) openDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", h.dbPath)
	if err != nil {
		t.Fatalf("sql.Open error = %v", err)
	}
	t.Cleanup(func() {
		closeErr := db.Close()
		if closeErr != nil {
			t.Errorf("close the test's database handle: %v", closeErr)
		}
	})
	return db
}

func (h *harness) playedGame(t *testing.T) (endReason sql.NullString, data string) {
	t.Helper()
	row := h.openDB(t).QueryRowContext(t.Context(), "SELECT end_reason, data FROM played_games WHERE id = ?", testGameID)
	err := row.Scan(&endReason, &data)
	if err != nil {
		t.Fatalf("read played_games row error = %v", err)
	}
	return endReason, data
}

func (h *harness) hasPlayedGame(t *testing.T) bool {
	t.Helper()
	var count int
	err := h.openDB(t).QueryRowContext(t.Context(), "SELECT COUNT(*) FROM played_games").Scan(&count)
	if err != nil {
		t.Fatalf("count played_games error = %v", err)
	}
	return count > 0
}

func (h *harness) replay(t *testing.T) []wire.Map {
	t.Helper()
	compressed, err := store.NewReplays(h.replayDir).Read(testGameID)
	if err != nil {
		t.Fatalf("Replays.Read error = %v", err)
	}
	return decodeReplay(t, compressed)
}

func intOf(t *testing.T, m wire.Map, k wire.Key) int {
	t.Helper()
	v, ok := m.Get(k)
	n, isInt := v.(wire.Int)
	if !ok || !isInt {
		t.Fatalf("%v has no integer %v", m, k)
	}
	return int(n)
}

func eventType(m wire.Map) (wire.EventType, bool) {
	v, ok := m.Get(wire.KeyEventType)
	n, isInt := v.(wire.Int)
	return wire.EventType(n), ok && isInt
}

func sessionType(m wire.Map) string {
	v, _ := m.Get(wire.KeySessionType)
	s, _ := v.(wire.Str)
	return string(s)
}

func ofEvent(messages []wire.Map, event wire.EventType) []wire.Map {
	var found []wire.Map
	for _, m := range messages {
		if got, ok := eventType(m); ok && got == event && sessionType(m) == "" {
			found = append(found, m)
		}
	}
	return found
}

func ofSession(messages []wire.Map, typ string) []wire.Map {
	var found []wire.Map
	for _, m := range messages {
		if sessionType(m) == typ {
			found = append(found, m)
		}
	}
	return found
}

func lastWaitID(t *testing.T, conn *fakeConn) int {
	t.Helper()
	for _, m := range slices.Backward(conn.messages()) {
		typ, _ := eventType(m)
		v, ok := m.Get(wire.KeyWaitID)
		if ok && typ != wire.EventError && sessionType(m) == "" {
			n, _ := v.(wire.Int)
			return int(n)
		}
	}
	t.Fatalf("no message to %s carries a wait id", conn.id)
	return 0
}

func decodeReplay(t *testing.T, compressed []byte) []wire.Map {
	t.Helper()
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		t.Fatalf("gzip.NewReader error = %v", err)
	}
	content, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("read replay error = %v", err)
	}
	records, err := wire.DecodeReplay(content)
	if err != nil {
		t.Fatalf("DecodeReplay error = %v", err)
	}
	return records
}

func drawnTile(t *testing.T, opening wire.Map) tile.TileID {
	t.Helper()
	_, drawn, err := wire.UnpackDraw(intOf(t, opening, wire.KeyPackedMove))
	if err != nil {
		t.Fatalf("UnpackDraw error = %v", err)
	}
	return drawn
}

func discard(waitID int, t tile.TileID) messaging.GameActionMessage {
	return messaging.GameActionMessage{
		Action: messaging.GameActionDiscard, WaitID: waitID, Play: play.Some(play.DiscardAction(t)),
	}
}

func seedSeating(t *testing.T, seats ...int) engine.Seed {
	t.Helper()
	var seed engine.Seed
	for n := range 1 << 16 {
		seed[0], seed[1] = byte(n), byte(n>>8)
		permutation := engine.SeatPermutation(seed)
		matches := true
		for i, want := range seats {
			matches = matches && permutation[i].Index() == want
		}
		if matches {
			return seed
		}
	}
	t.Fatalf("no seed seats players at %v", seats)
	return seed
}
