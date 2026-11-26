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

var ErrDatabasePath = errors.New("database path holds a '?'")

// DB is the shared SQLite database, open for the game server's writes. It is safe for concurrent
// use; its one connection runs one statement at a time, in WAL mode with a 5 s busy timeout.
type DB struct {
	conn   *sql.DB
	logger *slog.Logger
}

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
