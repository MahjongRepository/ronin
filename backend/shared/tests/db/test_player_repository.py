"""Tests for SqlitePlayerRepository."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from shared.auth.models import AccountType, Player
from shared.db.connection import Database
from shared.db.player_repository import SqlitePlayerRepository

if TYPE_CHECKING:
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
def repo(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.connect()
    yield SqlitePlayerRepository(db)
    db.close()


class TestCreateAndRead:
    async def test_create_and_get_by_username(self, repo: SqlitePlayerRepository) -> None:
        await repo.create_player(_human())
        result = await repo.get_by_username("alice")
        assert result is not None
        assert result.user_id == "u1"
        assert result.username == "alice"

    async def test_get_by_api_key_hash(self, repo: SqlitePlayerRepository) -> None:
        await repo.create_player(_bot())
        result = await repo.get_by_api_key_hash("keyhash1")
        assert result is not None
        assert result.username == "TestBot"
        assert result.account_type == AccountType.BOT

    async def test_get_by_username_returns_none_for_unknown(self, repo: SqlitePlayerRepository) -> None:
        assert await repo.get_by_username("nobody") is None

    async def test_get_by_api_key_hash_returns_none_for_unknown(self, repo: SqlitePlayerRepository) -> None:
        assert await repo.get_by_api_key_hash("unknown") is None


class TestDuplicateDetection:
    async def test_duplicate_id_raises_value_error(self, repo: SqlitePlayerRepository) -> None:
        await repo.create_player(_human())
        with pytest.raises(ValueError, match="already exists"):
            await repo.create_player(_human(username="bob"))

    async def test_duplicate_username_case_insensitive(self, repo: SqlitePlayerRepository) -> None:
        await repo.create_player(_human())
        with pytest.raises(ValueError, match="already taken"):
            await repo.create_player(_human(user_id="u2", username="ALICE"))

    async def test_duplicate_api_key_hash(self, repo: SqlitePlayerRepository) -> None:
        await repo.create_player(_bot())
        with pytest.raises(ValueError, match="API key hash already in use"):
            await repo.create_player(_bot(user_id="bot2", username="OtherBot", api_key_hash="keyhash1"))


class TestCaseInsensitiveUsername:
    async def test_lookup_case_insensitive(self, repo: SqlitePlayerRepository) -> None:
        await repo.create_player(_human(username="Alice"))
        assert await repo.get_by_username("alice") is not None
        assert await repo.get_by_username("ALICE") is not None
        assert await repo.get_by_username("aLiCe") is not None


class TestConcurrentAccess:
    async def test_concurrent_creates_all_succeed_or_raise_value_error(
        self,
        repo: SqlitePlayerRepository,
    ) -> None:
        """Concurrent creates with distinct ids/usernames all succeed; duplicates raise ValueError."""
        players = [_human(user_id=f"u{i}", username=f"user{i}") for i in range(10)]
        await asyncio.gather(*[repo.create_player(p) for p in players])

        for i in range(10):
            result = await repo.get_by_username(f"user{i}")
            assert result is not None
            assert result.user_id == f"u{i}"
