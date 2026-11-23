from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from app.db import schema

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def migrations_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "migrations"
    directory.mkdir()
    monkeypatch.setattr(schema, "MIGRATIONS_DIR", directory)
    return directory


@pytest.fixture
def old_database(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(tmp_path / "test.db", autocommit=True)) as conn:
        conn.execute("CREATE TABLE players (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO players VALUES ('alice')")
        yield conn


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def test_migrate__when_database_predates_the_ledger__should_apply_each_migration_once_in_name_order(
    migrations_dir: Path, old_database: sqlite3.Connection
):
    (migrations_dir / "0002_add_rating.sql").write_text("ALTER TABLE ratings ADD COLUMN rating REAL;\n")
    (migrations_dir / "0001_create_ratings.sql").write_text("CREATE TABLE ratings (player_id TEXT);\n")

    first = schema.migrate(old_database)
    second = schema.migrate(old_database)

    assert first == ["0001_create_ratings", "0002_add_rating"]
    assert second == []
    assert _columns(old_database, "ratings") == ["player_id", "rating"]
    assert old_database.execute("SELECT id FROM players").fetchall() == [("alice",)]


def test_migrate__when_a_migration_fails__should_roll_back_the_whole_batch_and_retry_it_next_time(
    migrations_dir: Path, old_database: sqlite3.Connection
):
    (migrations_dir / "0001_add_name.sql").write_text("ALTER TABLE players ADD COLUMN name TEXT;\n")
    broken = migrations_dir / "0002_add_rating.sql"
    broken.write_text("ALTER TABLE players ADD COLUMN rating REAL;\nALTER TABLE missing ADD COLUMN x REAL;\n")

    with pytest.raises(sqlite3.OperationalError):
        schema.migrate(old_database)
    assert _columns(old_database, "players") == ["id"]

    broken.write_text("ALTER TABLE players ADD COLUMN rating REAL;\n")
    retried = schema.migrate(old_database)

    assert retried == ["0001_add_name", "0002_add_rating"]
    assert _columns(old_database, "players") == ["id", "name", "rating"]
