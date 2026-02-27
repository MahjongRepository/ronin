"""SQLite database connection and schema management."""

import os
import sqlite3
from pathlib import Path

import structlog

logger = structlog.get_logger()

_DB_FILE_PERMISSIONS = 0o600

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    api_key_hash TEXT,
    data TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_username
    ON players (username COLLATE NOCASE);

CREATE UNIQUE INDEX IF NOT EXISTS idx_players_api_key_hash
    ON players (api_key_hash) WHERE api_key_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS played_games (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_played_games_started_at
    ON played_games (started_at DESC);
"""


class Database:
    """SQLite database wrapper with schema management."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the active connection or raise if disconnected."""
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    def connect(self) -> None:
        """Open the database, apply pragmas, create schema, and harden file permissions."""
        parent = Path(self._path).parent
        parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA_SQL)

        self._harden_permissions()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _harden_permissions(self) -> None:
        """Set restrictive file permissions on POSIX systems (best effort).

        Hardens the main DB file and WAL/SHM sibling files created by WAL mode,
        since they also contain database content (password and API-key hashes).
        """
        if os.name != "posix":  # pragma: no cover
            return
        for suffix in ("", "-wal", "-shm"):
            p = Path(self._path + suffix)
            if p.exists():
                try:
                    p.chmod(_DB_FILE_PERMISSIONS)
                except OSError:
                    logger.warning("could not set file permissions", permissions=oct(_DB_FILE_PERMISSIONS), path=str(p))
