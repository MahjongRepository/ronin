from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from shared.db.connection import Database

if TYPE_CHECKING:
    from pathlib import Path


class TestConnect:
    def test_database_connect__when_new_db__should_create_schema(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        db.connect()

        tables = db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "players" in table_names
        assert "played_games" in table_names

        db.close()

    def test_database_connection__when_not_connected__should_raise(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.connection

    def test_database_connect__when_parent_dirs_missing__should_create_them(self, tmp_path: Path):
        db = Database(tmp_path / "nested" / "dir" / "test.db")
        db.connect()
        assert db.connection is not None

        db.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
class TestPermissions:
    def test_database_connect__when_new_db__should_restrict_file_permissions(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.connect()

        mode = db_path.stat().st_mode & 0o777
        assert mode == 0o600

        db.close()

    def test_database_connect__when_chmod_fails__should_still_connect(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        with patch("pathlib.Path.chmod", side_effect=OSError("permission denied")):
            db.connect()
        # connect() should succeed despite chmod failure
        assert db.connection is not None

        db.close()
