package server_test

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	ticketSecret         = "test-ticket-secret"
	internalSecret       = "test-internal-secret"
	testGameID           = "game-0001"
	lobbyOrigin          = "http://lobby.test"
	testVersion          = "1.2.3"
	testCommit           = "abc1234"
	readTimeout          = 5 * time.Second
	fixedTicketExpiresAt = 4102444800
)

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
	t       *testing.T
	srv     *server.Server
	http    *httptest.Server
	dbPath  string
	replays replayfile.Dir
	logs    *lockedBuffer
	stopped bool
}

type option func(*server.Config, *session.Config)

func withSocket(edit func(*server.SocketConfig)) option {
	return func(c *server.Config, _ *session.Config) { edit(&c.Socket) }
}

func withCapacity(n int) option {
	return func(_ *server.Config, s *session.Config) { s.Capacity = n }
}

func newHarness(t *testing.T, options ...option) *harness {
	t.Helper()
	dir := t.TempDir()
	logs := &lockedBuffer{}
	logger := slog.New(slog.NewTextHandler(logs, &slog.HandlerOptions{Level: slog.LevelDebug}))
	dbPath := filepath.Join(dir, "game.db")
	db, err := store.Open(t.Context(), dbPath, logger)
	if err != nil {
		t.Fatalf("store.Open error = %v", err)
	}

	timing := session.DefaultTiming()
	timing.GameStartConfirm, timing.AITurnDelay = 0, 0
	replays := replayfile.New(filepath.Join(dir, "replays"))
	sessionCfg := session.Config{Timing: timing, Capacity: 10, DB: db, Replays: replays, Logger: logger}
	serverCfg := server.Config{
		Replays:        replays,
		TicketSecret:   ticketSecret,
		InternalSecret: internalSecret,
		CORSOrigins:    []string{lobbyOrigin},
		Version:        testVersion,
		Commit:         testCommit,
		Logger:         logger,
		Socket:         server.DefaultSocketConfig(),
	}
	for _, apply := range options {
		apply(&serverCfg, &sessionCfg)
	}
	manager, err := session.New(context.Background(), sessionCfg)
	if err != nil {
		t.Fatalf("session.New error = %v", err)
	}
	serverCfg.Session = manager
	srv, err := server.New(serverCfg)
	if err != nil {
		t.Fatalf("server.New error = %v", err)
	}

	h := &harness{t: t, srv: srv, http: httptest.NewServer(srv.Handler()), dbPath: dbPath, replays: replays, logs: logs}
	t.Cleanup(func() {
		h.shutdown()
		h.http.Close()
		closeErr := db.Close()
		if closeErr != nil {
			t.Errorf("db.Close error = %v", closeErr)
		}
		if strings.Contains(logs.String(), "level=ERROR") {
			t.Errorf("the server logged an error:\n%s", logs.String())
		}
	})
	return h
}

func (h *harness) shutdown() {
	if h.stopped {
		return
	}
	h.stopped = true
	err := h.srv.Shutdown(context.Background())
	if err != nil {
		h.t.Errorf("Shutdown error = %v", err)
	}
}

func ticketFor(gameID, name string) string {
	return auth.SignTicket(auth.Ticket{
		UserID:    "user-" + name,
		Username:  name,
		RoomID:    gameID,
		ExpiresAt: fixedTicketExpiresAt,
	}, ticketSecret)
}

type playerBody struct {
	Name   string `json:"name"`
	UserID string `json:"user_id"`
	Ticket string `json:"game_ticket"`
}

type createBody struct {
	GameID    string       `json:"game_id"`
	AIPlayers int          `json:"num_ai_players"`
	Players   []playerBody `json:"players"`
}

func gameBody(gameID string, names ...string) createBody {
	body := createBody{GameID: gameID, AIPlayers: 4 - len(names)}
	for _, name := range names {
		body.Players = append(body.Players, playerBody{Name: name, UserID: "user-" + name, Ticket: ticketFor(gameID, name)})
	}
	return body
}

type answer struct {
	status int
	header http.Header
	body   map[string]any
	text   string
}

func (h *harness) request(method, path string, body io.Reader, headers map[string]string) answer {
	h.t.Helper()
	req, err := http.NewRequestWithContext(h.t.Context(), method, h.http.URL+path, body)
	if err != nil {
		h.t.Fatalf("NewRequest error = %v", err)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := h.http.Client().Do(req)
	if err != nil {
		h.t.Fatalf("%s %s error = %v", method, path, err)
	}
	defer func() { _ = resp.Body.Close() }()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		h.t.Fatalf("read %s %s body: %v", method, path, err)
	}
	got := answer{status: resp.StatusCode, header: resp.Header, text: string(raw)}
	if len(raw) > 0 && strings.HasPrefix(resp.Header.Get("Content-Type"), "application/json") {
		err = json.Unmarshal(raw, &got.body)
		if err != nil {
			h.t.Fatalf("decode %s %s body %q: %v", method, path, raw, err)
		}
	}
	return got
}

func (h *harness) get(path string) answer {
	h.t.Helper()
	return h.request(http.MethodGet, path, nil, nil)
}

func (h *harness) internal(method, path string) answer {
	h.t.Helper()
	return h.request(method, path, nil, map[string]string{"Authorization": "Bearer " + internalSecret})
}

func (h *harness) postGame(body any) answer {
	h.t.Helper()
	raw, err := json.Marshal(body)
	if err != nil {
		h.t.Fatalf("encode body: %v", err)
	}
	return h.request(http.MethodPost, "/games", bytes.NewReader(raw), nil)
}

func (h *harness) create(names ...string) {
	h.t.Helper()
	got := h.postGame(gameBody(testGameID, names...))
	if got.status != http.StatusCreated {
		h.t.Fatalf("POST /games status = %d (%v), want %d", got.status, got.body, http.StatusCreated)
	}
}

func (h *harness) status() map[string]any {
	h.t.Helper()
	return h.get("/status").body
}

func (h *harness) dial(gameID string, header http.Header) *websocket.Conn {
	h.t.Helper()
	ws, _, err := websocket.Dial(h.t.Context(), "ws"+strings.TrimPrefix(h.http.URL, "http")+"/ws/"+gameID, &websocket.DialOptions{ //nolint:bodyclose // websocket.Dial closes the response body itself
		HTTPClient: h.http.Client(),
		HTTPHeader: header,
	})
	if err != nil {
		h.t.Fatalf("dial /ws/%s: %v", gameID, err)
	}
	h.t.Cleanup(func() { _ = ws.CloseNow() })
	return ws
}

func (h *harness) joinAlice() *websocket.Conn {
	h.t.Helper()
	ws := h.dial(testGameID, nil)
	send(h.t, ws, joinMessage(ticketFor(testGameID, "alice")))
	readUntil(h.t, ws, func(m wire.Map) bool { return sessionType(m) == "game_joined" })
	return ws
}

func joinMessage(ticket string) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientJoinGame)},
		{Key: wire.KeyGameTicket, Value: wire.Str(ticket)},
	}
}

func reconnectMessage(ticket string) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientReconnect)},
		{Key: wire.KeyGameTicket, Value: wire.Str(ticket)},
	}
}

func typed(typ messaging.ClientMessageType) wire.Map {
	return wire.Map{{Key: wire.KeyEventType, Value: wire.Int(typ)}}
}

func passOutsideAGame(waitID wire.Value) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(messaging.ClientGameAction)},
		{Key: wire.KeyWaitID, Value: waitID},
		{Key: wire.KeyAction, Value: wire.Int(messaging.GameActionPass)},
	}
}

func send(t *testing.T, ws *websocket.Conn, m wire.Map) {
	t.Helper()
	data, err := wire.Encode(m)
	if err != nil {
		t.Fatalf("encode %v: %v", m, err)
	}
	sendRaw(t, ws, data)
}

func sendRaw(t *testing.T, ws *websocket.Conn, data []byte) {
	t.Helper()
	err := ws.Write(t.Context(), websocket.MessageBinary, data)
	if err != nil {
		t.Fatalf("write frame: %v", err)
	}
}

func read(t *testing.T, ws *websocket.Conn) (wire.Map, error) {
	t.Helper()
	ctx, cancel := context.WithTimeout(t.Context(), readTimeout)
	defer cancel()
	_, data, err := ws.Read(ctx)
	if err != nil {
		return nil, err
	}
	m, err := wire.Decode(data)
	if err != nil {
		t.Fatalf("the server sent an undecodable message: %v", err)
	}
	return m, nil
}

func readMessage(t *testing.T, ws *websocket.Conn) wire.Map {
	t.Helper()
	m, err := read(t, ws)
	if err != nil {
		t.Fatalf("read message: %v", err)
	}
	return m
}

func readUntil(t *testing.T, ws *websocket.Conn, found func(wire.Map) bool) {
	t.Helper()
	for {
		if found(readMessage(t, ws)) {
			return
		}
	}
}

func readClose(t *testing.T, ws *websocket.Conn) websocket.CloseError {
	t.Helper()
	for {
		_, err := read(t, ws)
		if err == nil {
			continue
		}
		closed, ok := errors.AsType[websocket.CloseError](err)
		if !ok {
			t.Fatalf("read ended with %v, want a close frame", err)
		}
		return closed
	}
}

func awaitClose(t *testing.T, ws *websocket.Conn) <-chan error {
	t.Helper()
	closed := make(chan error, 1)
	go func() {
		for {
			_, _, err := ws.Read(t.Context())
			if err != nil {
				closed <- err
				return
			}
		}
	}()
	return closed
}

func sessionType(m wire.Map) string {
	v, _ := m.Get(wire.KeySessionType)
	s, _ := v.(wire.Str)
	return string(s)
}

func errorCode(m wire.Map) string {
	v, _ := m.Get(wire.KeySessionErrorCode)
	s, _ := v.(wire.Str)
	return string(s)
}

func isEvent(m wire.Map, event wire.EventType) bool {
	v, _ := m.Get(wire.KeyEventType)
	return v == wire.Int(event) && sessionType(m) == ""
}

func counter(t *testing.T, status map[string]any, key string) int {
	t.Helper()
	v, ok := status[key].(float64)
	if !ok {
		t.Fatalf("/status %s = %v, want a number", key, status[key])
	}
	return int(v)
}

func eventually(t *testing.T, condition func() bool) {
	t.Helper()
	deadline := time.Now().Add(readTimeout)
	for !condition() {
		if time.Now().After(deadline) {
			t.Fatal("the condition did not hold in time")
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func (h *harness) openDB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", h.dbPath)
	if err != nil {
		t.Fatalf("sql.Open error = %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

func noWaitID() play.Option[int] {
	return play.Option[int]{}
}

func some(n int) play.Option[int] {
	return play.Some(n)
}
