"""SQLite database connection and schema management."""

import json
import os
import sqlite3
from pathlib import Path

import structlog

from shared.auth.models import Player

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
"""


class Database:
    """SQLite database wrapper with schema management and migration support."""

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

    def migrate_from_json(self, legacy_json_path: str | None) -> int:
        """Migrate users from a legacy JSON file into the players table.

        Returns the number of players migrated. Skips migration when the path
        is None, the file does not exist, or the players table already has data.
        The entire migration runs in a single transaction; any failure causes
        a full rollback.
        """
        if legacy_json_path is None:
            return 0

        json_path = Path(legacy_json_path)
        if not json_path.exists():
            return 0

        conn = self.connection
        row = conn.execute("SELECT COUNT(*) FROM players").fetchone()
        if row[0] > 0:
            logger.info("players table already has data, skipping migration")
            return 0

        players = self._parse_legacy_json(json_path, legacy_json_path)
        self._insert_migrated_players(conn, players)

        count = len(players)
        logger.info("migrated players from legacy file", count=count, path=legacy_json_path)
        return count

    def _parse_legacy_json(self, json_path: Path, display_path: str) -> list[Player]:
        """Parse and validate the legacy JSON player file."""
        try:
            raw = json_path.read_text(encoding="utf-8")
        except OSError as exc:
            msg = f"Failed to read legacy JSON file: {display_path}"
            raise OSError(msg) from exc

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            msg = f"Malformed JSON in legacy file: {display_path}"
            raise OSError(msg) from exc

        if not isinstance(data, dict):
            msg = f"Expected JSON object at root in {display_path}"
            raise OSError(msg)

        players: list[Player] = []
        for uid, record in data.items():
            try:
                player = Player.model_validate(record)
            except ValueError as exc:
                msg = f"Invalid player record for key '{uid}' in {display_path}"
                raise OSError(msg) from exc

            if player.user_id != uid:
                msg = f"Key mismatch in {display_path}: dict key '{uid}' != player.user_id '{player.user_id}'"
                raise OSError(msg)
            players.append(player)

        return players

    @staticmethod
    def _insert_migrated_players(conn: sqlite3.Connection, players: list[Player]) -> None:
        """Insert all migrated players in a single transaction."""
        try:
            conn.execute("BEGIN")
            for player in players:
                conn.execute(
                    "INSERT INTO players (id, username, api_key_hash, data) VALUES (?, ?, ?, ?)",
                    (
                        player.user_id,
                        player.username,
                        player.api_key_hash,
                        player.model_dump_json(),
                    ),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

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
