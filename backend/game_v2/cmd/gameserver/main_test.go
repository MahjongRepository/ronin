package main

import (
	"database/sql"
	"errors"
	"io"
	"log/slog"
	"net"
	"path/filepath"
	"slices"
	"syscall"
	"testing"
	"time"

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
