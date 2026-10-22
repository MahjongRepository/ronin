from __future__ import annotations

import asyncio
import logging
import sqlite3
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from shared.db.connection import Database

if TYPE_CHECKING:
    from pathlib import Path


def _insert_marker(conn: sqlite3.Connection, marker: str) -> None:
    conn.execute("INSERT INTO players (id, username, data) VALUES (?, ?, '{}')", (marker, marker))


def _player_ids(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM players ORDER BY id")]


class TestOpen:
    async def test_database_open__when_parent_dirs_missing__should_create_them_and_the_schema(self, tmp_path: Path):
        db = Database(tmp_path / "nested" / "dir" / "test.db")
        await db.open()

        tables = await db.submit_read(
            lambda conn: [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")],
        )
        assert sorted(tables) == ["played_games", "players"]
        await db.close()

    async def test_database_open__when_opening_fails__should_raise_and_refuse_later_work(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        with (
            patch.object(Database, "_harden_permissions", side_effect=OSError("chmod refused")),
            pytest.raises(OSError, match="chmod refused"),
        ):
            await db.open()

        with pytest.raises(RuntimeError, match="not open"):
            db.submit_read(lambda conn: conn.execute("SELECT 1").fetchone())
        with pytest.raises(RuntimeError, match="opened only once"):
            await db.open()
        await db.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
class TestPermissions:
    async def test_database_open__when_new_db__should_restrict_file_permissions(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        await db.open()

        assert db_path.stat().st_mode & 0o777 == 0o600
        await db.close()

    async def test_database_open__when_chmod_fails__should_still_open(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        with patch("pathlib.Path.chmod", side_effect=OSError("permission denied")):
            await db.open()

        assert await db.submit_read(lambda conn: conn.execute("SELECT 1").fetchone()) == (1,)
        await db.close()


class TestWorker:
    async def test_database_write__when_it_fails__should_roll_back_and_raise_to_its_caller(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        await db.open()

        def insert_then_fail(conn: sqlite3.Connection) -> None:
            _insert_marker(conn, "rolled-back")
            raise ValueError("operation failed midway")

        with pytest.raises(ValueError, match="operation failed midway"):
            await db.submit_write(insert_then_fail)
        await db.submit_write(lambda conn: _insert_marker(conn, "committed"))

        assert _player_ids(db_path) == ["committed"]
        await db.close()

    async def test_database_post_write__when_it_fails_on_a_held_lock__should_log_the_operation_and_game(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        db_path = tmp_path / "test.db"
        db = Database(db_path, busy_timeout_ms=50)
        await db.open()
        other_server = sqlite3.connect(db_path, autocommit=True)

        other_server.execute("BEGIN IMMEDIATE")
        with caplog.at_level(logging.ERROR):
            db.post_write(lambda conn: _insert_marker(conn, "locked-out"), operation="create_game", game_id="g1")
            await db.submit_read(lambda conn: conn.execute("SELECT 1").fetchone())
        other_server.execute("COMMIT")

        failures = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert [(r.msg["event"], r.msg["operation"], r.msg["game_id"]) for r in failures] == [
            ("database write failed", "create_game", "g1"),
        ]
        assert str(failures[0].msg["exc_info"]) == "database is locked"
        assert _player_ids(db_path) == []
        other_server.close()
        await db.close()

    async def test_database_submit__when_its_caller_gave_up__should_still_run_it_and_the_jobs_after(
        self, tmp_path: Path
    ):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        await db.open()

        abandoned = db.submit_write(lambda conn: _insert_marker(conn, "abandoned"))
        abandoned.cancel()
        await db.submit_write(lambda conn: _insert_marker(conn, "next"))

        assert _player_ids(db_path) == ["abandoned", "next"]
        await db.close()

    async def test_database_close__when_posts_are_queued__should_run_them_before_closing(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        await db.open()

        for marker in ("a", "b", "c"):
            db.post_write(lambda conn, marker=marker: _insert_marker(conn, marker), operation="test")
        await db.close()

        assert _player_ids(db_path) == ["a", "b", "c"]
        with pytest.raises(RuntimeError, match="not open"):
            db.submit_write(lambda conn: _insert_marker(conn, "late"))

    async def test_database_post_write__when_closed__should_log_the_dropped_write(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        db = Database(tmp_path / "test.db")
        await db.open()
        await db.close()

        with caplog.at_level(logging.ERROR):
            db.post_write(lambda conn: _insert_marker(conn, "late"), operation="finish_game", game_id="g1")

        assert [(r.msg["event"], r.msg["operation"], r.msg["game_id"]) for r in caplog.records] == [
            ("database write dropped: the database is not open", "finish_game", "g1"),
        ]

    async def test_database_close__when_writes_outlast_the_drain_timeout__should_log_every_unfinished_game(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        db_path = tmp_path / "test.db"
        with pytest.raises(ValueError, match="outlast the busy timeout"):
            Database(db_path, busy_timeout_ms=50, drain_timeout_seconds=0.05)
        db = Database(db_path, busy_timeout_ms=50, drain_timeout_seconds=0.12)
        await db.open()
        other_server = sqlite3.connect(db_path, autocommit=True)

        other_server.execute("BEGIN IMMEDIATE")
        for game_id in ("g1", "g2", "g3", "g4"):
            db.post_write(
                lambda conn, game_id=game_id: _insert_marker(conn, game_id), operation="create_game", game_id=game_id
            )
        with caplog.at_level(logging.ERROR):
            await db.close()
            logged = [(r.msg["event"], r.msg.get("game_id"), str(r.msg.get("exc_info"))) for r in caplog.records]
        other_server.execute("COMMIT")

        assert ("database worker did not drain before shutdown", None, "None") in logged
        assert {game_id for _, game_id, _ in logged if game_id is not None} == {"g1", "g2", "g3", "g4"}
        assert (
            "database write failed",
            "g4",
            "dropped unrun: the database worker did not drain before shutdown",
        ) in logged
        other_server.close()

    async def test_database_open__when_cancelled__should_stop_its_worker(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")

        opening = asyncio.ensure_future(db.open())
        await asyncio.sleep(0)
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opening
        await db.close()

        assert db._thread is not None
        db._thread.join(timeout=5)
        assert not db._thread.is_alive()
