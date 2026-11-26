package main

import (
	"bytes"
	"compress/gzip"
	"io"
	"log/slog"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	playedGameID   = "game-0001"
	tamperedGameID = "game-0002"
	maxGameHours   = 24
)

type humanConn struct {
	mu     sync.Mutex
	closed bool
}

func (*humanConn) ID() string     { return "conn-1" }
func (*humanConn) GameID() string { return playedGameID }
func (*humanConn) Send([]byte)    {}

func (c *humanConn) Close(session.CloseCode, string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.closed = true
}

func (c *humanConn) isClosed() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.closed
}

func playSeededGame(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	replayDir := filepath.Join(dir, "replays")
	synctest.Test(t, func(t *testing.T) {
		logger := slog.New(slog.DiscardHandler)
		db, err := store.Open(t.Context(), filepath.Join(dir, "game.db"), logger)
		if err != nil {
			t.Fatalf("store.Open error = %v", err)
		}

		m, err := session.New(t.Context(), session.Config{
			Timing:   session.DefaultTiming(),
			Capacity: 1,
			DB:       db,
			Replays:  replayfile.New(replayDir),
			Logger:   logger,
			Seeds:    func() engine.Seed { return engine.Seed{0x5a, 17} },
		})
		if err != nil {
			t.Fatalf("session.New error = %v", err)
		}

		err = m.CreatePendingGame(playedGameID, []session.PlayerSpec{{Name: "Alice", UserID: "user-1", Ticket: "ticket-1"}}, session.SeatingShuffled)
		if err != nil {
			t.Fatalf("CreatePendingGame error = %v", err)
		}

		human := &humanConn{}
		m.Connect(human)
		m.Join(human, "ticket-1", play.Option[messaging.Claim]{})
		for hours := 0; !human.isClosed() && hours < maxGameHours; hours++ {
			time.Sleep(time.Hour)
			synctest.Wait()
		}

		if !human.isClosed() {
			t.Fatalf("the game did not end in %d hours", maxGameHours)
		}

		shutdownErr := m.Shutdown(t.Context())
		if shutdownErr != nil {
			t.Fatalf("Shutdown error = %v", shutdownErr)
		}

		closeErr := db.Close()
		if closeErr != nil {
			t.Fatalf("db.Close error = %v", closeErr)
		}
	})

	return replayDir
}

func storedRecords(t *testing.T, replays replayfile.Dir, gameID string) []wire.Map {
	t.Helper()
	compressed, err := replays.Read(gameID)
	if err != nil {
		t.Fatalf("Replays.Read error = %v", err)
	}

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

func runVerify(t *testing.T, replayDir string, ids ...string) (int, string) {
	t.Helper()
	var stdout, stderr strings.Builder
	code := run(ids, func(name string) string {
		if name == "GAME_REPLAY_DIR" {
			return replayDir
		}

		return ""
	}, &stdout, &stderr)
	if stderr.Len() > 0 {
		t.Errorf("verify wrote to stderr: %s", stderr.String())
	}

	return code, stdout.String()
}

func TestRun_WhenGivenAGameTheSessionPlayedToTheEnd_ShouldReproduceItsReplay(t *testing.T) {
	replayDir := playSeededGame(t)

	code, out := runVerify(t, replayDir, playedGameID)
	if want := "ok      " + playedGameID + "\n1/1 game(s) verified\n"; code != 0 || out != want {
		t.Errorf("verify = %d, %q, want 0, %q", code, out, want)
	}
}

func TestRun_WhenAStoredReplayDiffersFromItsRun_ShouldFailThatGameAtTheDifferingRecordAndExit1(t *testing.T) {
	replayDir := playSeededGame(t)
	replays := replayfile.New(replayDir)
	tests := []struct {
		name   string
		tamper func(t *testing.T, records []wire.Map) int
	}{
		{
			name: "round end altered",
			tamper: func(t *testing.T, records []wire.Map) int {
				t.Helper()
				rebindGameID(records)
				i := firstRecordOf(t, records, wire.EventRoundEnd)
				sticks, _ := records[i].Get(wire.KeyRiichiSticks)
				records[i] = with(records[i], wire.KeyRiichiSticks, sticks.(wire.Int)+1)
				return i
			},
		},
		{
			name: "draw altered",
			tamper: func(t *testing.T, records []wire.Map) int {
				t.Helper()
				rebindGameID(records)
				i := firstRecordOf(t, records, wire.EventDraw)
				left, _ := records[i].Get(wire.KeyTilesRemaining)
				records[i] = with(records[i], wire.KeyTilesRemaining, left.(wire.Int)+1)
				return i
			},
		},
		{
			name: "copied under another id",
			tamper: func(t *testing.T, records []wire.Map) int {
				t.Helper()
				return firstRecordOf(t, records, wire.EventGameStarted)
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			records := storedRecords(t, replays, playedGameID)
			position := tc.tamper(t, records) + 1
			content, err := wire.EncodeReplay(records)
			if err != nil {
				t.Fatalf("EncodeReplay error = %v", err)
			}

			saveErr := replays.Save(tamperedGameID, content)
			if saveErr != nil {
				t.Fatalf("Replays.Save error = %v", saveErr)
			}

			code, out := runVerify(t, replayDir, playedGameID, tamperedGameID)
			head := "ok      " + playedGameID + "\nFAILED  " + tamperedGameID + ": record " + strconv.Itoa(position) +
				" differs:\n"
			if code != 1 || !strings.HasPrefix(out, head) || !strings.HasSuffix(out, "\n1/2 game(s) verified\n") {
				t.Errorf("verify = %d, %q, want 1 with %s failing on record %d", code, out, tamperedGameID, position)
			}
		})
	}
}

func firstRecordOf(t *testing.T, records []wire.Map, event wire.EventType) int {
	t.Helper()
	for i, record := range records {
		if got, _ := record.Get(wire.KeyEventType); got == wire.Int(event) {
			return i
		}
	}

	t.Fatalf("the replay holds no record of event %d", event)
	return 0
}

func rebindGameID(records []wire.Map) {
	for i, record := range records {
		if event, _ := record.Get(wire.KeyEventType); event == wire.Int(wire.EventGameStarted) {
			records[i] = with(record, wire.KeyGameID, wire.Str(tamperedGameID))
		}
	}
}

func with(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	edited := make(wire.Map, 0, len(m))
	for _, f := range m {
		if f.Key == k {
			f.Value = v
		}

		edited = append(edited, f)
	}

	return edited
}
