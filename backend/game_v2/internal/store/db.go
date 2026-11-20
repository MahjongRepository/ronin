// Package store keeps what the game server persists beside the lobby: the `played_games` rows of
// the SQLite database both servers share, and the replay files the lobby serves.
//
// The lobby reads both, so their shapes are a contract. The game server creates only the table it
// writes, `played_games` with its index, in the lobby's own DDL; the lobby creates the rest of the
// schema when it opens the same file. A row's times keep the lobby's text forms, and its `data`
// keeps the JSON the lobby validates.
//
// Ported from ronin's Python shared storage: its database connection, game repository, played-game
// model and replay storage.
package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

const (
	databaseFileMode = 0o600
	databaseDirMode  = 0o750
	busyTimeout      = 5 * time.Second
)

const schemaSQL = `CREATE TABLE IF NOT EXISTS played_games (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_played_games_started_at
    ON played_games (started_at DESC);
`

// ErrDatabasePath is returned by Open for a path the SQLite driver would misread.
var ErrDatabasePath = errors.New("database path holds a '?'")

// DB is the shared SQLite database, open for the game server's writes. It is safe for concurrent
// use; its one connection runs one statement at a time, in WAL mode with a 5 s busy timeout.
type DB struct {
	conn   *sql.DB
	logger *slog.Logger
}

// Open opens the database at path, creating it and its directory when missing, creates the
// `played_games` table, and sets the file and its WAL and SHM siblings to owner-only access. A file
// whose permissions cannot be set is logged at warning level and left as it is. The logger, which
// also takes the DB's warnings, must not be nil.
func Open(ctx context.Context, path string, logger *slog.Logger) (*DB, error) {
	if strings.Contains(path, "?") {
		return nil, fmt.Errorf("open database %s: %w", path, ErrDatabasePath)
	}

	err := os.MkdirAll(filepath.Dir(path), databaseDirMode)
	if err != nil {
		return nil, fmt.Errorf("create database directory: %w", err)
	}

	dsn := fmt.Sprintf("%s?_busy_timeout=%d&_journal_mode=WAL&_foreign_keys=1", path, busyTimeout.Milliseconds())
	conn, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open database %s: %w", path, err)
	}
	conn.SetMaxOpenConns(1)

	_, err = conn.ExecContext(ctx, schemaSQL)
	if err != nil {
		return nil, errors.Join(fmt.Errorf("create schema in %s: %w", path, err), conn.Close())
	}

	hardenPermissions(path, logger)
	return &DB{conn: conn, logger: logger}, nil
}

// Close waits for the statements already running and closes the database.
func (db *DB) Close() error {
	return db.conn.Close()
}

func hardenPermissions(path string, logger *slog.Logger) {
	for _, suffix := range []string{"", "-wal", "-shm"} {
		file := path + suffix
		err := os.Chmod(file, databaseFileMode)
		if err != nil && !errors.Is(err, fs.ErrNotExist) {
			logger.Warn("could not set file permissions",
				"permissions", fmt.Sprintf("%O", databaseFileMode), "path", file, "error", err)
		}
	}
}
