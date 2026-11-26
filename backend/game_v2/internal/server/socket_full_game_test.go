package server_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	socketGameTimeout   = 30 * time.Second
	socketReadLimit     = 1 << 20
	unlimitedSocketRate = 1e9
	unlimitedBurst      = 1 << 30
)

type socketSchedule struct {
	script fullGameScript
	steps  []clientStep
	frames []int
}

func recordSocketSchedule(tb testing.TB) socketSchedule {
	tb.Helper()
	script := readFullGameScript(tb)
	table := openFullGameTable(tb, script)
	table.schedule = []clientStep{}

	conns, err := table.play(script, "schedule")
	if err != nil {
		tb.Fatalf("record the full game's schedule: %v", err)
	}

	return socketSchedule{script: script, steps: table.schedule, frames: sentCounts(conns)}
}

func (s socketSchedule) messages() int {
	total := 0
	for _, frames := range s.frames {
		total += frames
	}

	return total
}

type socketTable struct {
	http    *httptest.Server
	replays replayfile.Dir
}

func openSocketTable(tb testing.TB, script fullGameScript) *socketTable {
	tb.Helper()
	dir := tb.TempDir()
	logger := slog.New(slog.NewTextHandler(io.Discard, &slog.HandlerOptions{Level: slog.LevelInfo}))
	db, err := store.Open(context.Background(), filepath.Join(dir, "game.db"), logger)
	if err != nil {
		tb.Fatalf("store.Open error = %v", err)
	}

	replays := replayfile.New(filepath.Join(dir, "replays"))
	manager, err := session.New(context.Background(), session.Config{
		Timing:   session.DefaultTiming(),
		Capacity: 10,
		DB:       db,
		Replays:  replays,
		Logger:   logger,
		Seeds:    func() engine.Seed { return script.loaded.Seed },
	})
	if err != nil {
		tb.Fatalf("session.New error = %v", err)
	}

	socket := server.DefaultSocketConfig()
	socket.Rate, socket.Burst = unlimitedSocketRate, unlimitedBurst
	srv, err := server.New(server.Config{
		Session:        manager,
		Replays:        replays,
		TicketSecret:   ticketSecret,
		InternalSecret: internalSecret,
		CORSOrigins:    []string{lobbyOrigin},
		Logger:         logger,
		Socket:         socket,
	})
	if err != nil {
		tb.Fatalf("server.New error = %v", err)
	}

	table := &socketTable{http: httptest.NewServer(srv.Handler()), replays: replays}
	tb.Cleanup(func() {
		shutdownErr := srv.Shutdown(context.Background())
		table.http.Close()
		closeErr := errors.Join(shutdownErr, db.Close())
		if closeErr != nil {
			tb.Errorf("close the socket table: %v", closeErr)
		}
	})

	return table
}

type socketClient struct {
	ws       *websocket.Conn
	received atomic.Int64
	done     chan struct{}
	end      error
}

func (c *socketClient) read(ctx context.Context, changed chan<- struct{}) {
	defer close(c.done)
	for {
		_, r, err := c.ws.Reader(ctx)
		if err == nil {
			_, err = io.Copy(io.Discard, r)
		}
		if err != nil {
			c.end = err
			poke(changed)
			return
		}

		c.received.Add(1)
		poke(changed)
	}
}

func poke(changed chan<- struct{}) {
	select {
	case changed <- struct{}{}:
	default:
	}
}

func (t *socketTable) play(ctx context.Context, schedule socketSchedule, gameID string) error {
	ctx, cancel := context.WithTimeout(ctx, socketGameTimeout)
	defer cancel()

	tickets := make([]string, 0, len(schedule.script.names))
	for _, name := range schedule.script.names {
		tickets = append(tickets, ticketFor(gameID, name))
	}

	err := t.create(ctx, gameID, schedule.script.names, tickets)
	if err != nil {
		return err
	}

	changed := make(chan struct{}, 1)
	clients, err := t.dialAll(ctx, gameID, len(tickets), changed)
	defer stopClients(clients)
	if err != nil {
		return err
	}

	for _, step := range schedule.steps {
		err = awaitFrames(ctx, clients, step.after, changed)
		if err != nil {
			return err
		}

		message := step.message
		if step.join {
			message, err = wire.Encode(joinMessage(tickets[step.player]))
			if err != nil {
				return err
			}
		}

		err = clients[step.player].ws.Write(ctx, websocket.MessageBinary, message)
		if err != nil {
			return fmt.Errorf("client %d writes: %w", step.player, err)
		}
	}

	return awaitGameEnd(ctx, clients, schedule.frames)
}

func (t *socketTable) create(ctx context.Context, gameID string, names, tickets []string) error {
	body := createBody{GameID: gameID}
	for i, name := range names {
		body.Players = append(body.Players, playerBody{Name: name, UserID: "user-" + name, Ticket: tickets[i]})
	}

	raw, err := json.Marshal(body)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.http.URL+"/games", bytes.NewReader(raw))
	if err != nil {
		return err
	}

	resp, err := t.http.Client().Do(req)
	if err != nil {
		return fmt.Errorf("POST /games: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("POST /games status = %d, want %d", resp.StatusCode, http.StatusCreated)
	}

	return nil
}

func (t *socketTable) dialAll(ctx context.Context, gameID string, n int, changed chan<- struct{}) ([]*socketClient, error) {
	url := "ws" + strings.TrimPrefix(t.http.URL, "http") + "/ws/" + gameID
	clients := make([]*socketClient, 0, n)
	for range n {
		ws, _, err := websocket.Dial(ctx, url, &websocket.DialOptions{ //nolint:bodyclose // websocket.Dial closes the response body itself
			HTTPClient:      t.http.Client(),
			CompressionMode: websocket.CompressionDisabled,
		})
		if err != nil {
			return clients, fmt.Errorf("dial %s: %w", url, err)
		}

		ws.SetReadLimit(socketReadLimit)
		client := &socketClient{ws: ws, done: make(chan struct{})}
		clients = append(clients, client)
		go client.read(ctx, changed)
	}

	return clients, nil
}

func stopClients(clients []*socketClient) {
	for _, client := range clients {
		_ = client.ws.CloseNow()
	}

	for _, client := range clients {
		<-client.done
	}
}

func awaitFrames(ctx context.Context, clients []*socketClient, after []int, changed <-chan struct{}) error {
	for {
		if receivedAll(clients, after) {
			return nil
		}

		select {
		case <-changed:
		case <-ctx.Done():
			return fmt.Errorf("the clients received %v frames, want at least %v: %w", received(clients), after, ctx.Err())
		}
	}
}

func receivedAll(clients []*socketClient, after []int) bool {
	for i, client := range clients {
		if int(client.received.Load()) < after[i] {
			return false
		}
	}

	return true
}

func received(clients []*socketClient) []int {
	counts := make([]int, 0, len(clients))
	for _, client := range clients {
		counts = append(counts, int(client.received.Load()))
	}

	return counts
}

func awaitGameEnd(ctx context.Context, clients []*socketClient, frames []int) error {
	for i, client := range clients {
		select {
		case <-client.done:
		case <-ctx.Done():
			return fmt.Errorf("client %d still open once the script ran: %w", i, ctx.Err())
		}

		status := websocket.CloseStatus(client.end)
		if status != websocket.StatusCode(session.CloseGameEnded) {
			return fmt.Errorf("client %d ended, want close code %d: %w", i, session.CloseGameEnded, client.end)
		}
		if got := int(client.received.Load()); got != frames[i] {
			return fmt.Errorf("client %d received %d frames, want the %d the session sent in process", i, got, frames[i])
		}
	}

	return nil
}

func TestSocket_WhenFourClientsPlayTheFullGameFixture_ShouldSaveTheFixtureReplay(t *testing.T) {
	schedule := recordSocketSchedule(t)
	table := openSocketTable(t, schedule.script)

	err := table.play(t.Context(), schedule, fullGameFixtureID)
	if err != nil {
		t.Fatalf("play the full game over sockets: %v", err)
	}

	compressed, err := table.replays.Read(fullGameFixtureID)
	if err != nil {
		t.Fatalf("read the saved replay: %v", err)
	}

	saved, err := replayfile.Decompress(compressed, replayfile.MaxFileSize)
	if err != nil {
		t.Fatalf("decompress the saved replay: %v", err)
	}
	if !bytes.Equal(saved, schedule.script.fixture) {
		t.Errorf("the session saved %d replay bytes unlike the %d of the fixture", len(saved), len(schedule.script.fixture))
	}
}

func processCPU(tb testing.TB) time.Duration {
	tb.Helper()
	var usage syscall.Rusage
	err := syscall.Getrusage(syscall.RUSAGE_SELF, &usage)
	if err != nil {
		tb.Fatalf("getrusage: %v", err)
	}

	return time.Duration(usage.Utime.Nano() + usage.Stime.Nano())
}

func BenchmarkSocket_FullGame(b *testing.B) {
	schedule := recordSocketSchedule(b)
	table := openSocketTable(b, schedule.script)

	games := 0
	var cpu time.Duration
	for b.Loop() {
		games++
		start := processCPU(b)
		err := table.play(b.Context(), schedule, fmt.Sprintf("bench-%d", games))
		cpu += processCPU(b) - start
		if err != nil {
			b.Fatalf("play game %d: %v", games, err)
		}
	}

	b.ReportMetric(float64(schedule.script.steps), "steps/op")
	b.ReportMetric(float64(schedule.messages()), "messages/op")
	b.ReportMetric(float64(cpu.Nanoseconds())/float64(games), "cpu-ns/op")
}
