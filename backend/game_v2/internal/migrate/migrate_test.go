package migrate_test

import (
	"bytes"
	"compress/gzip"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/migrate"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const pythonRowsPath = "../store/testdata/python_rows.json"

type fixture struct {
	cfg migrate.Config
}

func newFixture(t *testing.T) fixture {
	t.Helper()
	dir := t.TempDir()
	cfg := migrate.Config{ReplayDir: filepath.Join(dir, "replays"), DatabasePath: filepath.Join(dir, "games.db"), Apply: true}
	for _, name := range legacyNames(t) {
		storeFile(t, cfg.ReplayDir, "fx_"+name, legacyContent(t, name))
	}

	db, err := store.Open(t.Context(), cfg.DatabasePath, slog.Default())
	if err != nil {
		t.Fatalf("Open: %v", err)
	}

	err = db.Close()
	if err != nil {
		t.Fatalf("Close: %v", err)
	}

	insertPythonRows(t, cfg.DatabasePath)
	return fixture{cfg: cfg}
}

func storeFile(t *testing.T, dir, gameID string, content []byte) {
	t.Helper()
	shard := filepath.Join(dir, gameID[:2], gameID[2:4])
	err := os.MkdirAll(shard, 0o700)
	if err != nil {
		t.Fatalf("mkdir %s: %v", shard, err)
	}

	var compressed bytes.Buffer
	writer := gzip.NewWriter(&compressed)
	_, err = writer.Write(content)
	if err == nil {
		err = writer.Close()
	}

	if err == nil {
		err = os.WriteFile(filepath.Join(shard, gameID+".msgpack.gz"), compressed.Bytes(), 0o600)
	}

	if err != nil {
		t.Fatalf("store %s: %v", gameID, err)
	}
}

func insertPythonRows(t *testing.T, path string) {
	t.Helper()
	var fixtures []struct {
		Row struct {
			ID        string  `json:"id"`
			StartedAt string  `json:"started_at"`
			EndedAt   *string `json:"ended_at"`
			EndReason *string `json:"end_reason"`
			Data      string  `json:"data"`
		} `json:"row"`
	}
	err := json.Unmarshal(readFile(t, pythonRowsPath), &fixtures)
	if err != nil {
		t.Fatalf("decode %s: %v", pythonRowsPath, err)
	}

	conn := openSQL(t, path)
	for _, f := range fixtures {
		_, err = conn.ExecContext(t.Context(),
			"INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?)",
			f.Row.ID, f.Row.StartedAt, f.Row.EndedAt, f.Row.EndReason, f.Row.Data)
		if err != nil {
			t.Fatalf("insert %s: %v", f.Row.ID, err)
		}
	}
}

func openSQL(t *testing.T, path string) *sql.DB {
	t.Helper()
	conn, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}

	t.Cleanup(func() {
		closeErr := conn.Close()
		if closeErr != nil {
			t.Errorf("close %s: %v", path, closeErr)
		}
	})

	return conn
}

func (f fixture) snapshot(t *testing.T) map[string]string {
	t.Helper()
	state := map[string]string{}
	err := filepath.WalkDir(f.cfg.ReplayDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil || entry.IsDir() {
			return walkErr
		}

		content, readErr := os.ReadFile(path)
		state[path] = string(content)
		return readErr
	})
	if err != nil {
		t.Fatalf("walk %s: %v", f.cfg.ReplayDir, err)
	}

	rows, err := openSQL(t, f.cfg.DatabasePath).QueryContext(t.Context(), "SELECT id, data FROM played_games")
	if err != nil {
		t.Fatalf("select rows: %v", err)
	}

	for rows.Next() {
		var id, data string
		err = rows.Scan(&id, &data)
		if err != nil {
			t.Fatalf("scan rows: %v", err)
		}

		state["row "+id] = data
	}

	readErr := errors.Join(rows.Err(), rows.Close())
	if readErr != nil {
		t.Fatalf("read rows: %v", readErr)
	}

	return state
}

func (f fixture) run(t *testing.T, cfg migrate.Config) (bool, string) {
	t.Helper()
	var out bytes.Buffer
	ok, err := migrate.Run(t.Context(), cfg, slog.Default(), &out)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}

	return ok, out.String()
}

func storedContent(t *testing.T, dir, gameID string) []byte {
	t.Helper()
	compressed, err := replayfile.New(dir).Read(gameID)
	if err != nil {
		t.Fatalf("read %s: %v", gameID, err)
	}

	content, err := replayfile.Decompress(compressed, wire.MaxReplayBytes)
	if err != nil {
		t.Fatalf("decompress %s: %v", gameID, err)
	}

	return content
}

func TestRun_WhenItRewritesTheOldReplays_ShouldStoreEachAsItsCommittedRewrite(t *testing.T) {
	f := newFixture(t)

	ok, out := f.run(t, f.cfg)
	if !ok || !strings.HasPrefix(out, "replays in "+f.cfg.ReplayDir+": 27 rewritten, 0 already current, 0 failed, 0 ignored\n") ||
		!strings.Contains(out, ": 1 converted to tenths, 0 already in tenths, 3 without final scores, 0 failed\n") {
		t.Errorf("Run = %v, report:\n%s", ok, out)
	}

	for _, name := range legacyNames(t) {
		want := readFile(t, filepath.Join(rewrittenDir, name+".msgpack"))
		if got := storedContent(t, f.cfg.ReplayDir, "fx_"+name); !bytes.Equal(got, want) {
			t.Errorf("stored %s = %x, want its committed rewrite", name, got)
		}
	}
}

func TestRun_WhenRunAgain_ShouldChangeNothing(t *testing.T) {
	f := newFixture(t)
	if firstOK, firstOut := f.run(t, f.cfg); !firstOK {
		t.Fatalf("first Run = false, report:\n%s", firstOut)
	}
	before := f.snapshot(t)

	ok, out := f.run(t, f.cfg)
	if diff := cmp.Diff(before, f.snapshot(t)); diff != "" {
		t.Errorf("the second run changed (-first +second):\n%s", diff)
	}

	if !ok || !strings.Contains(out, ": 0 rewritten, 27 already current, 0 failed, 0 ignored\n") ||
		!strings.Contains(out, ": 0 converted to tenths, 1 already in tenths, 3 without final scores, 0 failed\n") {
		t.Errorf("second Run = %v, report:\n%s", ok, out)
	}
}

func TestRun_WhenItIsADryRun_ShouldReportTheRunAndWriteNothing(t *testing.T) {
	f := newFixture(t)
	before := f.snapshot(t)
	cfg := f.cfg
	cfg.Apply = false

	ok, out := f.run(t, cfg)
	if diff := cmp.Diff(before, f.snapshot(t)); diff != "" {
		t.Errorf("the dry run changed (-before +after):\n%s", diff)
	}

	if !ok || !strings.Contains(out, ": 27 rewritten,") || !strings.Contains(out, ": 1 converted to tenths,") ||
		!strings.HasSuffix(out, "dry run: nothing written\n") {
		t.Errorf("dry Run = %v, report:\n%s", ok, out)
	}
}

func TestRun_WhenAReplayCannotBeRewritten_ShouldLeaveItReportItAndFail(t *testing.T) {
	f := newFixture(t)
	broken := legacyEdited(t, "kans", func(events []wire.Map) []wire.Map {
		return append(events, wire.Map{{Key: wire.KeyEventType, Value: wire.Int(wire.EventPaoAssigned)}})
	})

	storeFile(t, f.cfg.ReplayDir, "broken", broken)
	storeFile(t, filepath.Join(f.cfg.ReplayDir, "fx"), "misplaced", legacyContent(t, "kans"))
	err := os.WriteFile(filepath.Join(f.cfg.ReplayDir, "fx", ".replay_left.tmp"), nil, 0o600)
	if err != nil {
		t.Fatalf("write a temp file: %v", err)
	}

	ok, out := f.run(t, f.cfg)
	if got := storedContent(t, f.cfg.ReplayDir, "broken"); !bytes.Equal(got, broken) {
		t.Errorf("the broken replay was changed to %x", got)
	}

	wantLines := []string{
		": 27 rewritten, 0 already current, 1 failed, 2 ignored\n",
		"  failed as unknown shape: 1\n",
		"  failed replay broken: unknown shape at record 32: a record of an event type replay version 0.4-dev never held\n",
		"  ignored fx/.replay_left.tmp\n",
		"  ignored fx/mi/sp/misplaced.msgpack.gz\n",
	}
	for _, line := range wantLines {
		if !strings.Contains(out, line) {
			t.Errorf("report lacks %q:\n%s", line, out)
		}
	}

	if ok {
		t.Error("Run = true, want false for a failed replay")
	}
}

func TestRun_WhenTheDatabaseIsMissing_ShouldCreateNothingAndRefuse(t *testing.T) {
	f := newFixture(t)
	cfg := f.cfg
	cfg.DatabasePath = filepath.Join(t.TempDir(), "missing.db")

	_, err := migrate.Run(t.Context(), cfg, slog.Default(), &bytes.Buffer{})
	if !errors.Is(err, fs.ErrNotExist) {
		t.Errorf("Run error = %v, want one matching fs.ErrNotExist", err)
	}

	if _, statErr := os.Stat(cfg.DatabasePath); !errors.Is(statErr, fs.ErrNotExist) {
		t.Errorf("the missing database was created: %v", statErr)
	}
}

func TestRun_WhenTheContextIsDone_ShouldStopBeforeRewritingAReplay(t *testing.T) {
	f := newFixture(t)
	before := f.snapshot(t)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()

	_, err := migrate.Run(ctx, f.cfg, slog.Default(), &bytes.Buffer{})
	if !errors.Is(err, context.Canceled) {
		t.Errorf("Run error = %v, want %v", err, context.Canceled)
	}

	if diff := cmp.Diff(before, f.snapshot(t)); diff != "" {
		t.Errorf("the cancelled run changed (-before +after):\n%s", diff)
	}
}
