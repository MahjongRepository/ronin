"""Tests for Database connection, schema, and migration."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from shared.auth.models import AccountType, Player
from shared.db.connection import Database

if TYPE_CHECKING:
    from pathlib import Path

FAKE_BCRYPT_HASH = "$2b$12$fakehash"


def _human_player(user_id: str = "u1", username: str = "alice") -> Player:
    return Player(user_id=user_id, username=username, password_hash=FAKE_BCRYPT_HASH)


def _bot_player(user_id: str = "bot1", username: str = "TestBot") -> Player:
    return Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash="abc123hash",
    )


def _write_legacy_json(path: Path, players: dict[str, Player]) -> None:
    data = {uid: player.model_dump() for uid, player in players.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class TestConnect:
    def test_creates_schema_and_connects(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        db.connect()

        tables = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "players" in table_names
        assert "played_games" in table_names
        db.close()

    def test_reconnect_after_close(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        db.connect()
        db.close()
        db.connect()

        tables = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        ).fetchall()
        assert len([t for t in tables if t[0] in ("players", "played_games")]) == 2
        db.close()

    def test_connection_raises_when_disconnected(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.connection

    def test_connection_raises_after_close(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        db.connect()
        db.close()
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.connection

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "nested" / "dir" / "test.db")
        db.connect()
        assert db.connection is not None
        db.close()


class TestMigration:
    def test_migrates_players_from_legacy_json(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        _write_legacy_json(json_path, {"u1": _human_player(), "bot1": _bot_player()})

        db = Database(tmp_path / "test.db")
        db.connect()
        count = db.migrate_from_json(str(json_path))

        assert count == 2
        row = db.connection.execute("SELECT COUNT(*) FROM players").fetchone()
        assert row[0] == 2
        db.close()

    def test_returns_zero_when_path_is_none(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        db.connect()
        assert db.migrate_from_json(None) == 0
        db.close()

    def test_returns_zero_when_file_missing(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        db.connect()
        assert db.migrate_from_json(str(tmp_path / "nonexistent.json")) == 0
        db.close()

    def test_skips_when_players_table_nonempty(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        _write_legacy_json(json_path, {"u1": _human_player()})

        db = Database(tmp_path / "test.db")
        db.connect()

        db.migrate_from_json(str(json_path))

        count = db.migrate_from_json(str(json_path))
        assert count == 0
        row = db.connection.execute("SELECT COUNT(*) FROM players").fetchone()
        assert row[0] == 1
        db.close()

    def test_rollback_on_invalid_record(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        json_path.write_text(
            json.dumps(
                {
                    "u1": _human_player().model_dump(),
                    "bad": {"invalid": "data"},
                },
            ),
        )

        db = Database(tmp_path / "test.db")
        db.connect()
        with pytest.raises(OSError, match="Invalid player record"):
            db.migrate_from_json(str(json_path))

        row = db.connection.execute("SELECT COUNT(*) FROM players").fetchone()
        assert row[0] == 0
        db.close()

    def test_rollback_on_key_mismatch(self, tmp_path: Path) -> None:
        player = _human_player(user_id="real_id")
        json_path = tmp_path / "users.json"
        json_path.write_text(json.dumps({"wrong_key": player.model_dump()}))

        db = Database(tmp_path / "test.db")
        db.connect()
        with pytest.raises(OSError, match="Key mismatch"):
            db.migrate_from_json(str(json_path))

        row = db.connection.execute("SELECT COUNT(*) FROM players").fetchone()
        assert row[0] == 0
        db.close()

    def test_raises_on_malformed_root_json(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        json_path.write_text("[]")

        db = Database(tmp_path / "test.db")
        db.connect()
        with pytest.raises(OSError, match="Expected JSON object"):
            db.migrate_from_json(str(json_path))
        db.close()

    def test_raises_on_corrupt_json(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        json_path.write_text("{not valid json")

        db = Database(tmp_path / "test.db")
        db.connect()
        with pytest.raises(OSError, match="Malformed JSON"):
            db.migrate_from_json(str(json_path))
        db.close()

    def test_raises_on_unreadable_file(self, tmp_path: Path) -> None:
        json_path = tmp_path / "users.json"
        json_path.write_text("{}")
        json_path.chmod(0o000)

        db = Database(tmp_path / "test.db")
        db.connect()
        with pytest.raises(OSError, match="Failed to read legacy JSON file"):
            db.migrate_from_json(str(json_path))
        db.close()
        json_path.chmod(0o644)

    def test_insert_migrated_players_rolls_back_on_duplicate(self, tmp_path: Path) -> None:
        """_insert_migrated_players rolls back the transaction on IntegrityError."""
        db = Database(tmp_path / "test.db")
        db.connect()
        player = _human_player()
        # Passing the same player twice triggers IntegrityError on the second INSERT,
        # which exercises the except -> ROLLBACK -> raise path (lines 149-151).
        with pytest.raises(sqlite3.IntegrityError):
            Database._insert_migrated_players(db.connection, [player, player])

        row = db.connection.execute("SELECT COUNT(*) FROM players").fetchone()
        assert row[0] == 0
        db.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
class TestPermissions:
    def test_db_file_has_restricted_permissions(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.connect()

        mode = db_path.stat().st_mode & 0o777
        assert mode == 0o600
        db.close()

    def test_harden_permissions_warns_on_failure(self, tmp_path: Path) -> None:
        """Permission hardening logs a warning on failure instead of raising."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        with patch("pathlib.Path.chmod", side_effect=OSError("permission denied")):
            db.connect()
        # connect() should succeed despite chmod failure
        assert db.connection is not None
        db.close()
