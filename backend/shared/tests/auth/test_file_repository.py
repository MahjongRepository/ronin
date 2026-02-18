"""Tests for FileUserRepository."""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from shared.auth.file_repository import FileUserRepository
from shared.auth.models import AccountType, User

if TYPE_CHECKING:
    from pathlib import Path

FAKE_BCRYPT_HASH = "$2b$12$fakehash"


def _human_user(user_id="u1", username="alice", pw_hash=FAKE_BCRYPT_HASH) -> User:
    return User(user_id=user_id, username=username, password_hash=pw_hash)


def _bot_user(user_id="bot1", username="TestBot", api_key_hash="abc123hash") -> User:
    return User(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=api_key_hash,
    )


class TestCreateUser:
    async def test_creates_and_retrieves_user(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        user = _human_user()
        await repo.create_user(user)

        result = await repo.get_by_username("alice")
        assert result is not None
        assert result.username == "alice"
        assert result.user_id == "u1"

    async def test_rejects_duplicate_user_id(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        await repo.create_user(_human_user())

        with pytest.raises(ValueError, match="already exists"):
            await repo.create_user(_human_user(username="bob"))

    async def test_rejects_duplicate_username_case_insensitive(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        await repo.create_user(_human_user())

        with pytest.raises(ValueError, match="already taken"):
            await repo.create_user(_human_user(user_id="u2", username="Alice"))

    async def test_persists_to_file(self, tmp_path: Path):
        file_path = tmp_path / "users.json"
        repo = FileUserRepository(file_path)
        await repo.create_user(_human_user())

        assert file_path.exists()
        data = json.loads(file_path.read_text())
        assert "u1" in data
        assert data["u1"]["username"] == "alice"

    async def test_creates_parent_directories(self, tmp_path: Path):
        file_path = tmp_path / "nested" / "dir" / "users.json"
        repo = FileUserRepository(file_path)
        await repo.create_user(_human_user())

        assert file_path.exists()


class TestGetByUsername:
    async def test_finds_user_case_insensitive(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        await repo.create_user(_human_user())

        result = await repo.get_by_username("ALICE")
        assert result is not None
        assert result.user_id == "u1"

    async def test_returns_none_for_unknown(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        assert await repo.get_by_username("nobody") is None


class TestGetByApiKeyHash:
    async def test_finds_bot_by_api_key_hash(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        await repo.create_user(_bot_user())

        result = await repo.get_by_api_key_hash("abc123hash")
        assert result is not None
        assert result.username == "TestBot"
        assert result.account_type == AccountType.BOT

    async def test_returns_none_for_unknown_hash(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")
        assert await repo.get_by_api_key_hash("unknown") is None


class TestFilePersistence:
    async def test_loads_existing_data_on_startup(self, tmp_path: Path):
        file_path = tmp_path / "users.json"
        user = _human_user()
        data = {"u1": user.model_dump()}
        file_path.write_text(json.dumps(data))

        repo = FileUserRepository(file_path)
        result = await repo.get_by_username("alice")
        assert result is not None
        assert result.username == "alice"

    async def test_raises_on_empty_file(self, tmp_path: Path):
        file_path = tmp_path / "users.json"
        file_path.write_text("")

        repo = FileUserRepository(file_path)
        with pytest.raises(OSError, match="Failed to load"):
            await repo.get_by_username("alice")

    async def test_raises_on_corrupt_json(self, tmp_path: Path):
        file_path = tmp_path / "users.json"
        file_path.write_text("{invalid json")

        repo = FileUserRepository(file_path)
        with pytest.raises(OSError, match="Failed to load"):
            await repo.get_by_username("alice")

    async def test_handles_nonexistent_file(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "missing.json")
        assert await repo.get_by_username("alice") is None


class TestLoadMalformedJson:
    async def test_raises_on_non_dict_json_root(self, tmp_path: Path):
        """JSON file containing an array instead of an object raises on load."""
        file_path = tmp_path / "users.json"
        file_path.write_text("[]")

        repo = FileUserRepository(file_path)
        with pytest.raises(OSError, match="Expected JSON object"):
            await repo.get_by_username("alice")

    async def test_raises_on_invalid_user_data_in_dict(self, tmp_path: Path):
        """Valid dict JSON but user data that fails Pydantic validation raises on load."""
        file_path = tmp_path / "users.json"
        file_path.write_text(json.dumps({"u1": {"bad": "data"}}))

        repo = FileUserRepository(file_path)
        with pytest.raises(OSError, match="Failed to parse user data"):
            await repo.get_by_username("alice")


class TestLoadUnreadableFile:
    async def test_raises_on_unreadable_file(self, tmp_path: Path):
        """An existing file that cannot be read raises on load."""
        file_path = tmp_path / "users.json"
        file_path.write_text("{}")
        file_path.chmod(0o000)

        repo = FileUserRepository(file_path)
        with pytest.raises(OSError, match="Failed to load"):
            await repo.get_by_username("alice")

        # Restore permissions for cleanup
        file_path.chmod(0o644)


class TestDataLossPrevention:
    async def test_corrupt_file_blocks_create_preventing_data_loss(self, tmp_path: Path):
        """When existing file is corrupt, create_user raises instead of overwriting with empty data."""
        file_path = tmp_path / "users.json"
        file_path.write_text("{corrupt data")

        repo = FileUserRepository(file_path)
        with pytest.raises(OSError, match="Failed to load"):
            await repo.create_user(_human_user())

        # The corrupt file is preserved, not overwritten
        assert file_path.read_text() == "{corrupt data"

    async def test_saved_file_has_restricted_permissions(self, tmp_path: Path):
        file_path = tmp_path / "users.json"
        repo = FileUserRepository(file_path)
        await repo.create_user(_human_user())

        mode = file_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestCreateUserRollback:
    async def test_rollback_on_save_failure(self, tmp_path: Path):
        """If file save fails, in-memory state is not mutated."""
        file_path = tmp_path / "users.json"
        repo = FileUserRepository(file_path)

        # Create an initial user successfully
        await repo.create_user(_human_user())

        # Make the file path a directory so write_text fails with OSError
        bad_path = tmp_path / "broken.json"
        bad_path.mkdir()
        repo._file_path = bad_path

        with pytest.raises(IsADirectoryError):
            await repo.create_user(_human_user(user_id="u2", username="bob"))

        # The failed user should not be in memory
        assert repo._users.get("u2") is None
        # The original user should still be there
        assert repo._users.get("u1") is not None

    async def test_cleanup_on_write_failure(self, tmp_path: Path):
        """If file write fails, temp file is cleaned up."""
        file_path = tmp_path / "users.json"
        repo = FileUserRepository(file_path)

        real_fdopen = os.fdopen

        def failing_fdopen(fd, mode="r", *args, **kwargs):
            f = real_fdopen(fd, mode, *args, **kwargs)

            def bad_write(_data):
                raise OSError("disk full")

            f.write = bad_write
            return f

        with patch("os.fdopen", side_effect=failing_fdopen), pytest.raises(OSError, match="disk full"):
            await repo.create_user(_human_user())


class TestConcurrentAccess:
    async def test_concurrent_creates_do_not_lose_data(self, tmp_path: Path):
        repo = FileUserRepository(tmp_path / "users.json")

        users = [_human_user(user_id=f"u{i}", username=f"user{i}") for i in range(10)]
        await asyncio.gather(*[repo.create_user(u) for u in users])

        for i in range(10):
            result = await repo.get_by_username(f"user{i}")
            assert result is not None
            assert result.user_id == f"u{i}"
