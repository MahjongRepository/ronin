package main

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

func leaves(err error) []error {
	if err == nil {
		return nil
	}

	joined, ok := err.(interface{ Unwrap() []error })
	if !ok {
		return []error{err}
	}

	var all []error
	for _, part := range joined.Unwrap() {
		all = append(all, leaves(part)...)
	}

	return all
}

func TestUnlogged_WhenPartsOfTheErrorWereLogged_ShouldKeepOnlyTheOthers(t *testing.T) {
	failure := errors.New("open database")
	logClose := errors.New("close the log file")
	profileClose := errors.New("close the CPU profile")
	tests := []struct {
		name string
		err  error
		want []error
	}{
		{
			"close errors joined to a logged run",
			errors.Join(errors.Join(loggedError{failure}, logClose), profileClose),
			[]error{logClose, profileClose},
		},
		{"a bare logged run", loggedError{failure}, nil},
		{"a plain failure", failure, []error{failure}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := unlogged(tc.err)
			if !slices.Equal(leaves(got), tc.want) {
				t.Errorf("unlogged(%q) = %q, want the parts %q", tc.err, got, tc.want)
			}
		})
	}
}

func TestRunLogged_WhenTheAddressIsTaken_ShouldFailBeforeClosingUnfinishedGames(t *testing.T) {
	logger := slog.New(slog.DiscardHandler)
	cfg := config{databasePath: filepath.Join(t.TempDir(), "games.db"), replayDir: t.TempDir()}
	db, err := store.Open(t.Context(), cfg.databasePath, logger)
	if err != nil {
		t.Fatal(err)
	}

	start := store.GameStart{GameID: "game-unfinished", StartedAt: time.Now(), GameType: "hanchan"}
	err = errors.Join(db.RecordStart(t.Context(), start), db.Close())
	if err != nil {
		t.Fatal(err)
	}

	taken, err := (&net.ListenConfig{}).Listen(t.Context(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer closeChecked(t, taken)

	err = runLogged(t.Context(), taken.Addr().String(), cfg, logger)
	if !errors.Is(err, syscall.EADDRINUSE) {
		t.Errorf("runLogged error = %v, want the address in use", err)
	}
	if got := unfinishedRows(t, cfg.databasePath); got != 1 {
		t.Errorf("unfinished rows = %d, want the seeded 1", got)
	}
}

func TestServe_WhenServingFails_ShouldShutTheServerDownBeforeReturning(t *testing.T) {
	srv, cfg := testServer(t)
	listener, err := (&net.ListenConfig{}).Listen(t.Context(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	closeChecked(t, listener)

	err = serve(t.Context(), listener, srv, slog.New(slog.DiscardHandler), func() {})
	if !errors.Is(err, net.ErrClosed) {
		t.Fatalf("serve error = %v, want the closed listener", err)
	}

	httpServer := httptest.NewServer(srv.Handler())
	t.Cleanup(httpServer.Close)
	request, err := http.NewRequestWithContext(
		t.Context(), http.MethodPost, httpServer.URL+"/games", gameRequest(t, cfg.ticketSecret),
	)
	if err != nil {
		t.Fatal(err)
	}

	answer, err := httpServer.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer closeChecked(t, answer.Body)

	if answer.StatusCode != http.StatusServiceUnavailable {
		t.Errorf("POST /games after a failed serve = %d, want 503", answer.StatusCode)
	}
}

func TestServe_WhenARequestIsStillOpenAtShutdown_ShouldCloseSocketsWithoutWaitingForIt(t *testing.T) {
	srv, _ := testServer(t)
	listener, err := (&net.ListenConfig{}).Listen(t.Context(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}

	ctx, stop := context.WithCancel(t.Context())
	served := make(chan error, 1)
	go func() {
		served <- serve(ctx, listener, srv, slog.New(slog.DiscardHandler), func() {})
	}()

	base := "http://" + listener.Addr().String()
	ws, _, err := websocket.Dial(t.Context(), "ws"+strings.TrimPrefix(base, "http")+"/ws/game-0001", nil) //nolint:bodyclose // websocket.Dial closes the response body itself
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = ws.CloseNow() }()

	request, err := (&net.Dialer{}).DialContext(t.Context(), "tcp", listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer closeChecked(t, request)

	answers := bufio.NewReader(request)
	_, err = io.WriteString(request, "POST /games HTTP/1.1\r\nHost: game\r\nContent-Length: 2\r\nExpect: 100-continue\r\n\r\n")
	if err != nil {
		t.Fatal(err)
	}

	status, err := answers.ReadString('\n')
	if err != nil || !strings.Contains(status, "100 Continue") {
		t.Fatalf("interim answer = %q, %v; want 100 Continue once the handler reads the body", status, err)
	}

	_, err = answers.ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}

	stop()
	_, _, err = ws.Read(t.Context())
	if code := websocket.CloseStatus(err); code != websocket.StatusServiceRestart {
		t.Errorf("socket read = %v, want close 1012", err)
	}

	err = request.SetReadDeadline(time.Now())
	if err != nil {
		t.Fatal(err)
	}

	_, err = answers.ReadString('\n')
	if !errors.Is(err, os.ErrDeadlineExceeded) {
		t.Errorf("request answer read = %v, want the request still open when the socket closed", err)
	}

	_, err = io.WriteString(request, "{}")
	if err != nil {
		t.Fatal(err)
	}

	err = <-served
	if err != nil {
		t.Errorf("serve error = %v, want a clean shutdown", err)
	}
}

func testServer(t *testing.T) (*server.Server, config) {
	t.Helper()
	logger := slog.New(slog.DiscardHandler)
	cfg := config{
		capacity:       1,
		replayDir:      t.TempDir(),
		ticketSecret:   "ticket-secret",
		internalSecret: "internal-secret",
		socket:         server.DefaultSocketConfig(),
	}
	db, err := store.Open(t.Context(), filepath.Join(t.TempDir(), "games.db"), logger)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeChecked(t, db) })

	srv, err := newServer(t.Context(), cfg, db, logger)
	if err != nil {
		t.Fatal(err)
	}

	return srv, cfg
}

func gameRequest(t *testing.T, ticketSecret string) io.Reader {
	t.Helper()
	const gameID = "game-0001"
	ticket := auth.SignTicket(auth.Ticket{
		UserID:    "user-alice",
		Username:  "alice",
		RoomID:    gameID,
		ExpiresAt: float64(time.Now().Add(time.Hour).Unix()),
	}, ticketSecret)
	body, err := json.Marshal(map[string]any{
		"game_id":        gameID,
		"num_ai_players": 3,
		"players":        []map[string]string{{"name": "alice", "user_id": "user-alice", "game_ticket": ticket}},
	})
	if err != nil {
		t.Fatal(err)
	}

	return strings.NewReader(string(body))
}

func unfinishedRows(t *testing.T, path string) int {
	t.Helper()
	conn, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer closeChecked(t, conn)

	var count int
	err = conn.QueryRowContext(t.Context(), "SELECT COUNT(*) FROM played_games WHERE ended_at IS NULL").Scan(&count)
	if err != nil {
		t.Fatal(err)
	}

	return count
}

func closeChecked(t *testing.T, c io.Closer) {
	t.Helper()
	err := c.Close()
	if err != nil {
		t.Errorf("close: %v", err)
	}
}
