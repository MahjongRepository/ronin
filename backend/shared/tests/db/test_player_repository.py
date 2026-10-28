from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from shared.dal.models import AccountType, Player
from shared.db.connection import Database
from shared.db.player_repository import SqlitePlayerRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

FAKE_BCRYPT_HASH = "$2b$12$fakehash"


def _human(user_id: str = "u1", username: str = "alice") -> Player:
    return Player(user_id=user_id, username=username, password_hash=FAKE_BCRYPT_HASH)


def _bot(user_id: str = "bot1", username: str = "TestBot", api_key_hash: str = "keyhash1") -> Player:
    return Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=api_key_hash,
    )


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[SqlitePlayerRepository]:
    db = Database(tmp_path / "test.db")
    await db.open()
    yield SqlitePlayerRepository(db)
    await db.close()


class TestCreateAndRead:
    async def test_player_repository__when_human_created__should_find_by_username(self, repo: SqlitePlayerRepository):
        await repo.create_player(_human())

        result = await repo.get_by_username("alice")
        assert result is not None
        assert result.user_id == "u1"
        assert result.username == "alice"

    async def test_player_repository__when_bot_created__should_find_by_api_key_hash(self, repo: SqlitePlayerRepository):
        await repo.create_player(_bot())

        result = await repo.get_by_api_key_hash("keyhash1")
        assert result is not None
        assert result.username == "TestBot"
        assert result.account_type == AccountType.BOT

    async def test_player_repository__when_username_unknown__should_return_none(self, repo: SqlitePlayerRepository):
        assert await repo.get_by_username("nobody") is None

    async def test_player_repository__when_api_key_hash_unknown__should_return_none(self, repo: SqlitePlayerRepository):
        assert await repo.get_by_api_key_hash("unknown") is None


class TestDuplicateDetection:
    async def test_player_repository__when_user_id_duplicated__should_raise(self, repo: SqlitePlayerRepository):
        await repo.create_player(_human())
        with pytest.raises(ValueError, match="already exists"):
            await repo.create_player(_human(username="bob"))

    async def test_player_repository__when_username_differs_only_by_case__should_raise(
        self, repo: SqlitePlayerRepository
    ):
        await repo.create_player(_human())
        with pytest.raises(ValueError, match="already taken"):
            await repo.create_player(_human(user_id="u2", username="ALICE"))

    async def test_player_repository__when_api_key_hash_duplicated__should_raise(self, repo: SqlitePlayerRepository):
        await repo.create_player(_bot())
        with pytest.raises(ValueError, match="API key hash already in use"):
            await repo.create_player(_bot(user_id="bot2", username="OtherBot", api_key_hash="keyhash1"))


class TestSetApiKeyHash:
    async def test_player_repository_set_api_key_hash__when_player_exists__should_find_it_only_by_the_new_hash(
        self, repo: SqlitePlayerRepository
    ):
        await repo.create_player(_bot())

        await repo.set_api_key_hash("bot1", "keyhash2")
        assert (await repo.get_by_api_key_hash("keyhash2")).user_id == "bot1"
        assert await repo.get_by_api_key_hash("keyhash1") is None
        assert (await repo.get_by_username("TestBot")).api_key_hash == "keyhash2"

    async def test_player_repository_set_api_key_hash__when_player_id_unknown__should_raise(
        self, repo: SqlitePlayerRepository
    ):
        with pytest.raises(ValueError, match="does not exist"):
            await repo.set_api_key_hash("nobody", "keyhash2")


class TestCaseInsensitiveUsername:
    async def test_player_repository__when_username_case_differs__should_find_player(
        self, repo: SqlitePlayerRepository
    ):
        await repo.create_player(_human(username="Alice"))

        assert await repo.get_by_username("alice") is not None
        assert await repo.get_by_username("ALICE") is not None
        assert await repo.get_by_username("aLiCe") is not None


async def test_player_repository__when_a_write_failed_on_a_held_lock__should_keep_the_connection_usable(tmp_path: Path):
    db_path = tmp_path / "test.db"
    db = Database(db_path, busy_timeout_ms=50)
    await db.open()
    repo = SqlitePlayerRepository(db)
    other_server = sqlite3.connect(db_path, autocommit=True)

    other_server.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        await repo.create_player(_human(user_id="u1", username="alice"))
    other_server.execute("COMMIT")

    assert await repo.get_by_username("alice") is None
    other_server.execute(
        "INSERT INTO players (id, username, data) VALUES (?, ?, ?)",
        ("u2", "carol", _human(user_id="u2", username="carol").model_dump_json()),
    )
    await repo.create_player(_human(user_id="u3", username="bob"))

    assert await repo.get_by_username("carol") is not None
    assert other_server.execute("SELECT id FROM players WHERE username = 'bob'").fetchall() == [("u3",)]
    other_server.close()
    await db.close()
