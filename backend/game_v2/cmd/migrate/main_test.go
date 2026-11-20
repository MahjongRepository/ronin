package main

import (
	"bytes"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

func emptyStack(t *testing.T) map[string]string {
	t.Helper()
	dir := t.TempDir()
	env := map[string]string{
		"GAME_REPLAY_DIR":    filepath.Join(dir, "replays"),
		"AUTH_DATABASE_PATH": filepath.Join(dir, "games.db"),
	}
	err := os.Mkdir(env["GAME_REPLAY_DIR"], 0o700)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	db, err := store.Open(t.Context(), env["AUTH_DATABASE_PATH"], slog.New(slog.DiscardHandler))
	if err == nil {
		err = db.Close()
	}
	if err != nil {
		t.Fatalf("create the database: %v", err)
	}
	return env
}

func TestRun_WhenTheStackIsGivenByItsEnvironment_ShouldDryRunItAndPassWithNothingToMigrate(t *testing.T) {
	env := emptyStack(t)
	var stdout, stderr bytes.Buffer

	code := run(t.Context(), []string{"-dry-run"}, func(k string) string { return env[k] }, &stdout, &stderr)

	if code != 0 || !strings.Contains(stdout.String(), ": 0 rewritten, 0 already current, 0 failed, 0 ignored\n") ||
		!strings.HasSuffix(stdout.String(), "dry run: nothing written\n") {
		t.Errorf("run = %d, stdout:\n%s\nstderr:\n%s", code, stdout.String(), stderr.String())
	}
}

func TestRun_WhenTheDatabaseIsMissing_ShouldFailWithoutAReport(t *testing.T) {
	env := emptyStack(t)
	var stdout, stderr bytes.Buffer

	code := run(t.Context(), []string{"-database", filepath.Join(t.TempDir(), "missing.db")},
		func(k string) string { return env[k] }, &stdout, &stderr)

	if code != exitFailed || stdout.Len() != 0 || !strings.Contains(stderr.String(), "migration did not complete") {
		t.Errorf("run = %d, stdout %q, stderr %q; want exit %d with the error logged", code, stdout.String(), stderr.String(), exitFailed)
	}
}

func TestRun_WhenNoReplayDirectoryIsGiven_ShouldRefuseTheUsage(t *testing.T) {
	var stderr bytes.Buffer

	code := run(t.Context(), nil, func(string) string { return "" }, &bytes.Buffer{}, &stderr)

	if code != exitUsage || !strings.Contains(stderr.String(), "migrate needs a replay directory") {
		t.Errorf("run = %d, stderr %q; want exit %d", code, stderr.String(), exitUsage)
	}
}
