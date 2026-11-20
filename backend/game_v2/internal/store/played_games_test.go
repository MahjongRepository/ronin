package store_test

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

const pythonRowsPath = "testdata/python_rows.json"

type playedGameRow struct {
	ID        string  `json:"id"`
	StartedAt string  `json:"started_at"`
	EndedAt   *string `json:"ended_at"`
	EndReason *string `json:"end_reason"`
	Data      string  `json:"data"`
}

var (
	fixtureSeats = []store.Player{
		{Name: "alice", UserID: "5f0c2d1e-8b7a-4c3d-9e2f-1a0b3c4d5e6f"},
		{Name: "Tsumogiri 1"},
		{Name: "Алиса <&>", UserID: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"},
		{Name: "Tsumogiri 2"},
	}
	fixtureStartedAt   = time.Date(2026, 11, 19, 10, 0, 0, 123456789, time.UTC)
	fixtureWholeSecond = time.Date(2026, 11, 19, 10, 0, 0, 0, time.UTC)
	fixtureEndedAt     = time.Date(2026, 11, 19, 13, 42, 7, 5000, time.FixedZone("UTC+3", 3*60*60))
	fixtureResult      = store.Result{
		RoundsPlayed: 9,
		Placements: []store.Placement{
			{Seat: 2, Score: 42300, FinalScore: 523},
			{Seat: 0, Score: 28100, FinalScore: 81},
			{Seat: 3, Score: 18600, FinalScore: -214},
			{Seat: 1, Score: 11000, FinalScore: -390},
		},
	}
)

func fixtureStart(gameID string, startedAt time.Time) store.GameStart {
	return store.GameStart{GameID: gameID, StartedAt: startedAt, GameType: "hanchan", Seats: fixtureSeats}
}

func openDB(t *testing.T, logs *bytes.Buffer) (*store.DB, string) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "data", "games.db")
	db, err := store.Open(t.Context(), path, slog.New(slog.NewTextHandler(logs, nil)))
	if err != nil {
		t.Fatalf("Open(%s): %v", path, err)
	}
	t.Cleanup(func() {
		closeErr := db.Close()
		if closeErr != nil {
			t.Errorf("Close: %v", closeErr)
		}
	})
	return db, path
}

func closeChecked(t *testing.T, c io.Closer) {
	t.Helper()
	err := c.Close()
	if err != nil {
		t.Errorf("close: %v", err)
	}
}

func readRows(t *testing.T, path string) map[string]playedGameRow {
	t.Helper()
	conn, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer closeChecked(t, conn)

	rows, err := conn.QueryContext(t.Context(), "SELECT id, started_at, ended_at, end_reason, data FROM played_games")
	if err != nil {
		t.Fatalf("select played_games: %v", err)
	}
	defer closeChecked(t, rows)

	byID := map[string]playedGameRow{}
	for rows.Next() {
		var r playedGameRow
		err = rows.Scan(&r.ID, &r.StartedAt, &r.EndedAt, &r.EndReason, &r.Data)
		if err != nil {
			t.Fatalf("scan played_games: %v", err)
		}
		byID[r.ID] = r
	}
	if rows.Err() != nil {
		t.Fatalf("read played_games: %v", rows.Err())
	}
	return byID
}

func TestOpen_WhenTheDatabaseIsNew_ShouldCreateOnlyPlayedGamesWithOwnerOnlyFiles(t *testing.T) {
	_, path := openDB(t, &bytes.Buffer{})

	conn, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer closeChecked(t, conn)

	var names []string
	rows, err := conn.QueryContext(t.Context(), "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name")
	if err != nil {
		t.Fatalf("select sqlite_master: %v", err)
	}
	defer closeChecked(t, rows)
	for rows.Next() {
		var name string
		err = rows.Scan(&name)
		if err != nil {
			t.Fatalf("scan sqlite_master: %v", err)
		}
		names = append(names, name)
	}
	if want := []string{"idx_played_games_started_at", "played_games"}; !slices.Equal(names, want) {
		t.Errorf("schema objects = %v, want %v", names, want)
	}

	var journalMode string
	err = conn.QueryRowContext(t.Context(), "PRAGMA journal_mode").Scan(&journalMode)
	if err != nil || journalMode != "wal" {
		t.Errorf("journal_mode = %q, %v; want wal", journalMode, err)
	}

	for _, suffix := range []string{"", "-wal", "-shm"} {
		info, statErr := os.Stat(path + suffix)
		if statErr != nil || info.Mode().Perm() != 0o600 {
			t.Errorf("%s mode = %v, %v; want 0600", path+suffix, info, statErr)
		}
	}
}

func TestOpen_WhenThePathHoldsAQueryMark_ShouldRefuseIt(t *testing.T) {
	_, err := store.Open(t.Context(), filepath.Join(t.TempDir(), "games.db?mode=ro"), slog.Default())
	if !errors.Is(err, store.ErrDatabasePath) {
		t.Errorf("Open error = %v, want %v", err, store.ErrDatabasePath)
	}
}

func TestDB_WhenPlayingThePythonFixtureGames_ShouldWriteThePythonRowsMarkedInTenths(t *testing.T) {
	content, err := os.ReadFile(pythonRowsPath)
	if err != nil {
		t.Fatalf("read %s: %v", pythonRowsPath, err)
	}
	var fixtures []struct {
		Name string        `json:"name"`
		Row  playedGameRow `json:"row"`
	}
	err = json.Unmarshal(content, &fixtures)
	if err != nil {
		t.Fatalf("decode %s: %v", pythonRowsPath, err)
	}

	db, path := openDB(t, &bytes.Buffer{})
	ctx := t.Context()
	games := map[string]func() error{
		"started": func() error {
			return db.RecordStart(ctx, fixtureStart("game-started", fixtureStartedAt))
		},
		"completed": func() error {
			start := fixtureStart("game-completed", fixtureStartedAt)
			return errors.Join(db.RecordStart(ctx, start), db.RecordCompleted(ctx, start, fixtureEndedAt, fixtureResult))
		},
		"abandoned_whole_seconds": func() error {
			start := fixtureStart("game-abandoned", fixtureWholeSecond)
			return errors.Join(db.RecordStart(ctx, start), db.RecordAbandoned(ctx, start, fixtureWholeSecond))
		},
		"failed": func() error {
			start := fixtureStart("game-failed", fixtureStartedAt)
			return errors.Join(db.RecordStart(ctx, start), db.RecordFailed(ctx, start, fixtureEndedAt))
		},
	}
	for _, f := range fixtures {
		err = games[f.Name]()
		if err != nil {
			t.Fatalf("%s: record: %v", f.Name, err)
		}
	}

	rows := readRows(t, path)
	for _, f := range fixtures {
		want := f.Row
		want.Data = strings.TrimSuffix(want.Data, "}") + `,"final_score_unit":"tenths"}`
		if diff := cmp.Diff(want, rows[f.Row.ID]); diff != "" {
			t.Errorf("%s: row differs from Python's marked in tenths (-python +go):\n%s", f.Name, diff)
		}
	}
}

func TestRecordStart_WhenTheGameIsAlreadyRecorded_ShouldRefuseItWithErrGameRecordedAndKeepTheFirstRow(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	first := fixtureStart("game-twice", fixtureStartedAt)
	second := fixtureStart("game-twice", fixtureWholeSecond)
	second.Seats = fixtureSeats[:1]

	err := db.RecordStart(t.Context(), first)
	if err != nil {
		t.Fatalf("first RecordStart: %v", err)
	}
	err = db.RecordStart(t.Context(), second)
	if !errors.Is(err, store.ErrGameRecorded) {
		t.Errorf("second RecordStart error = %v, want ErrGameRecorded", err)
	}

	row := rowOf(t, path, "game-twice")
	if row.StartedAt != "2026-11-19T10:00:00.123456+00:00" || !strings.Contains(row.Data, `"Tsumogiri 2"`) {
		t.Errorf("row = %+v, want the first start's", row)
	}
}

func TestRecordFinish_WhenTheGameAlreadyFinished_ShouldKeepTheFirstFinishAndWarn(t *testing.T) {
	var logs bytes.Buffer
	db, path := openDB(t, &logs)
	start := fixtureStart("game-done", fixtureStartedAt)

	err := errors.Join(
		db.RecordStart(t.Context(), start),
		db.RecordCompleted(t.Context(), start, fixtureEndedAt, fixtureResult),
		db.RecordFailed(t.Context(), start, fixtureWholeSecond),
	)
	if err != nil {
		t.Fatalf("record: %v", err)
	}

	row := rowOf(t, path, "game-done")
	if row.EndReason == nil || *row.EndReason != "completed" || !strings.Contains(row.Data, `"final_score":523`) {
		t.Errorf("row = %+v, want the completed finish", row)
	}
	if !strings.Contains(logs.String(), `msg="game already finished, keeping its first finish" game_id=game-done`) {
		t.Errorf("logs = %q, want the ignored finish's warning", logs.String())
	}
}

func TestRecordFinish_WhenTheStartWasNeverRecorded_ShouldWriteTheWholeRow(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	start := fixtureStart("game-unstarted", fixtureStartedAt)

	err := db.RecordAbandoned(t.Context(), start, fixtureEndedAt)
	if err != nil {
		t.Fatalf("RecordAbandoned: %v", err)
	}

	row := rowOf(t, path, "game-unstarted")
	if row.StartedAt != "2026-11-19T10:00:00.123456+00:00" || row.EndReason == nil || *row.EndReason != "abandoned" {
		t.Errorf("row = %+v, want the abandoned game's whole row", row)
	}
}

func TestRecordCompleted_WhenAPlacementSeatHasNoPlayer_ShouldRefuseIt(t *testing.T) {
	db, path := openDB(t, &bytes.Buffer{})
	start := fixtureStart("game-bad-seat", fixtureStartedAt)
	result := store.Result{RoundsPlayed: 8, Placements: []store.Placement{{Seat: 4}}}

	err := db.RecordCompleted(t.Context(), start, fixtureEndedAt, result)
	if !errors.Is(err, store.ErrUnknownSeat) {
		t.Errorf("RecordCompleted error = %v, want %v", err, store.ErrUnknownSeat)
	}
	if rows := readRows(t, path); len(rows) != 0 {
		t.Errorf("rows = %v, want none", rows)
	}
}

func rowOf(t *testing.T, path, gameID string) playedGameRow {
	t.Helper()
	row, ok := readRows(t, path)[gameID]
	if !ok {
		t.Fatalf("no row for %s", gameID)
	}
	return row
}
