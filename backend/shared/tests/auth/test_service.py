from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from shared.auth.password import BcryptHasher
from shared.auth.service import AuthError, AuthService
from shared.auth.session_store import AuthSessionStore
from shared.dal.models import AccountType, Player
from shared.db import Database, SqlitePlayerRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
def session_store():
    return AuthSessionStore()


@pytest.fixture
async def player_repo(tmp_path: Path) -> AsyncIterator[SqlitePlayerRepository]:
    db = Database(tmp_path / "test.db")
    await db.open()
    yield SqlitePlayerRepository(db)
    await db.close()


@pytest.fixture
def auth_service(player_repo, session_store):
    return AuthService(player_repo, session_store, password_hasher=BcryptHasher(rounds=4))


class TestRegister:
    async def test_auth_service_register__when_valid__should_create_human_player(self, auth_service):
        player = await auth_service.register("alice", "password123")
        assert player.username == "alice"
        assert player.account_type == AccountType.HUMAN
        assert player.user_id

    async def test_auth_service_register__when_username_taken__should_raise(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="already taken"):
            await auth_service.register("alice", "otherpassword1")

    async def test_auth_service_register__when_username_differs_only_by_case__should_raise(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="already taken"):
            await auth_service.register("Alice", "otherpassword1")

    async def test_auth_service_register__when_username_too_short__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("ab", "password123")

    async def test_auth_service_register__when_username_too_long__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("a" * 31, "password123")

    async def test_auth_service_register__when_username_has_special_chars__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="letters, numbers, and underscores"):
            await auth_service.register("alice!", "password123")

    async def test_auth_service_register__when_password_too_short__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("alice", "short")

    async def test_auth_service_register__when_password_too_long__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("alice", "x" * 73)

    async def test_auth_service_register__when_password_exceeds_72_bytes__should_raise(self, auth_service):
        # 25 CJK characters = 25 chars but 75 UTF-8 bytes, exceeding bcrypt's 72-byte limit
        with pytest.raises(AuthError, match="bytes"):
            await auth_service.register("alice", "\u3042" * 25)


class TestRegisterBot:
    async def test_auth_service_register_bot__when_valid__should_return_player_and_hashed_api_key(self, auth_service):
        player, raw_api_key = await auth_service.register_bot("MyBot")
        assert player.username == "MyBot"
        assert player.account_type == AccountType.BOT
        assert player.password_hash == "!"
        assert player.api_key_hash is not None
        assert raw_api_key
        # The raw key hashes to the stored hash
        expected_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
        assert player.api_key_hash == expected_hash

    async def test_auth_service_register_bot__when_name_taken__should_raise(self, auth_service):
        await auth_service.register_bot("UniqueBot")

        with pytest.raises(AuthError, match="already taken"):
            await auth_service.register_bot("UniqueBot")

    async def test_auth_service_register_bot__when_name_invalid__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register_bot("ab")


class TestLogin:
    async def test_auth_service_login__when_credentials_valid__should_return_session(self, auth_service):
        await auth_service.register("alice", "password123")

        session = await auth_service.login("alice", "password123")
        assert session.username == "alice"
        assert session.session_id

    async def test_auth_service_login__when_human__should_create_human_session(self, auth_service):
        await auth_service.register("alice", "password123")
        session = await auth_service.login("alice", "password123")
        assert session.account_type == AccountType.HUMAN

    async def test_auth_service_login__when_password_wrong__should_raise(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="Invalid credentials"):
            await auth_service.login("alice", "wrongpassword")

    async def test_auth_service_login__when_player_unknown__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="Invalid credentials"):
            await auth_service.login("nobody", "password123")

    async def test_auth_service_login__when_account_is_bot__should_raise(self, auth_service, player_repo):
        bot = Player(
            user_id="bot-1",
            username="TestBot",
            password_hash="!",
            account_type=AccountType.BOT,
            api_key_hash="somehash",
        )
        await player_repo.create_player(bot)

        with pytest.raises(AuthError, match="Invalid credentials"):
            await auth_service.login("TestBot", "anything1")


class TestValidateSession:
    async def test_auth_service_validate_session__when_active__should_return_session(self, auth_service):
        await auth_service.register("alice", "password123")
        session = await auth_service.login("alice", "password123")

        result = auth_service.validate_session(session.session_id)
        assert result is not None
        assert result.username == "alice"

    def test_auth_service_validate_session__when_id_unknown__should_return_none(self, auth_service):
        assert auth_service.validate_session("nonexistent") is None

    def test_auth_service_validate_session__when_id_is_none__should_return_none(self, auth_service):
        assert auth_service.validate_session(None) is None


class TestCreateSession:
    def test_auth_service_create_session__when_no_account_type__should_default_to_human(self, auth_service):
        session = auth_service.create_session(user_id="user-1", username="alice")
        assert session.account_type == AccountType.HUMAN

    def test_auth_service_create_session__when_bot__should_keep_account_type(self, auth_service):
        session = auth_service.create_session(user_id="bot-1", username="TestBot", account_type=AccountType.BOT)
        assert session.account_type == AccountType.BOT


class TestLogout:
    async def test_auth_service_logout__when_session_exists__should_invalidate_it(self, auth_service):
        await auth_service.register("alice", "password123")
        session = await auth_service.login("alice", "password123")

        auth_service.logout(session.session_id)
        assert auth_service.validate_session(session.session_id) is None


class TestRegisterConcurrentRace:
    async def test_auth_service_register__when_repo_reports_duplicate__should_raise_auth_error(self, auth_service):
        error = ValueError("Username already taken")
        with (
            patch.object(auth_service._player_repo, "create_player", new_callable=AsyncMock, side_effect=error),
            patch.object(auth_service._player_repo, "get_by_username", new_callable=AsyncMock, return_value=None),
            pytest.raises(AuthError, match="already taken"),
        ):
            await auth_service.register("raceuser", "password123")


class TestValidateApiKey:
    async def _create_bot(self, player_repo, username: str = "ValidBot") -> tuple[Player, str]:
        raw_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        bot = Player(
            user_id=f"bot-{username.lower()}",
            username=username,
            password_hash="!",
            account_type=AccountType.BOT,
            api_key_hash=api_key_hash,
        )
        await player_repo.create_player(bot)
        return bot, raw_key

    async def test_auth_service_validate_api_key__when_key_valid__should_return_bot(self, auth_service, player_repo):
        bot, raw_key = await self._create_bot(player_repo)

        result = await auth_service.validate_api_key(raw_key)
        assert result is not None
        assert result.user_id == bot.user_id
        assert result.account_type == AccountType.BOT

    async def test_auth_service_validate_api_key__when_key_bogus__should_return_none(self, auth_service):
        result = await auth_service.validate_api_key("totally-bogus-key")
        assert result is None

    async def test_auth_service_validate_api_key__when_key_wrong__should_return_none(self, auth_service, player_repo):
        await self._create_bot(player_repo, username="KeyBot")

        result = await auth_service.validate_api_key("wrong-key-value")
        assert result is None


class TestSessionStoreRequired:
    async def test_auth_service_login__when_no_session_store__should_raise(self, player_repo):
        svc = AuthService(player_repo, password_hasher=BcryptHasher(rounds=4))
        await svc.register("alice", "password123")
        with pytest.raises(RuntimeError, match="session_store is required"):
            await svc.login("alice", "password123")
