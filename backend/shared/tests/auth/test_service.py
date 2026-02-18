"""Tests for AuthService."""

from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from shared.auth.file_repository import FileUserRepository
from shared.auth.models import AccountType, User
from shared.auth.service import AuthError, AuthService
from shared.auth.session_store import AuthSessionStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def session_store():
    return AuthSessionStore()


@pytest.fixture
async def user_repo(tmp_path: Path):
    return FileUserRepository(tmp_path / "users.json")


@pytest.fixture
def auth_service(user_repo, session_store):
    return AuthService(user_repo, session_store)


class TestRegister:
    async def test_registers_human_user(self, auth_service):
        user = await auth_service.register("alice", "password123")

        assert user.username == "alice"
        assert user.account_type == AccountType.HUMAN
        assert user.user_id

    async def test_rejects_duplicate_username(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="already taken"):
            await auth_service.register("alice", "otherpassword1")

    async def test_rejects_duplicate_username_case_insensitive(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="already taken"):
            await auth_service.register("Alice", "otherpassword1")

    async def test_rejects_short_username(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("ab", "password123")

    async def test_rejects_long_username(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("a" * 31, "password123")

    async def test_rejects_username_with_special_chars(self, auth_service):
        with pytest.raises(AuthError, match="letters, numbers, and underscores"):
            await auth_service.register("alice!", "password123")

    async def test_rejects_short_password(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("alice", "short")

    async def test_rejects_long_password(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register("alice", "x" * 73)

    async def test_rejects_multibyte_password_exceeding_72_bytes(self, auth_service):
        # 25 CJK characters = 25 chars but 75 UTF-8 bytes, exceeding bcrypt's 72-byte limit
        with pytest.raises(AuthError, match="bytes"):
            await auth_service.register("alice", "\u3042" * 25)


class TestLogin:
    async def test_login_success(self, auth_service):
        await auth_service.register("alice", "password123")
        session = await auth_service.login("alice", "password123")

        assert session.username == "alice"
        assert session.session_id

    async def test_login_wrong_password(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="Invalid credentials"):
            await auth_service.login("alice", "wrongpassword")

    async def test_login_unknown_user(self, auth_service):
        with pytest.raises(AuthError, match="Invalid credentials"):
            await auth_service.login("nobody", "password123")

    async def test_login_rejects_bot_account(self, auth_service, user_repo):
        bot = User(
            user_id="bot-1",
            username="TestBot",
            password_hash="!",
            account_type=AccountType.BOT,
            api_key_hash="somehash",
        )
        await user_repo.create_user(bot)

        with pytest.raises(AuthError, match="Invalid credentials"):
            await auth_service.login("TestBot", "anything1")


class TestValidateSession:
    async def test_validates_active_session(self, auth_service):
        await auth_service.register("alice", "password123")
        session = await auth_service.login("alice", "password123")

        result = auth_service.validate_session(session.session_id)
        assert result is not None
        assert result.username == "alice"

    def test_returns_none_for_invalid_id(self, auth_service):
        assert auth_service.validate_session("nonexistent") is None

    def test_returns_none_for_none(self, auth_service):
        assert auth_service.validate_session(None) is None


class TestLogout:
    async def test_logout_destroys_session(self, auth_service):
        await auth_service.register("alice", "password123")
        session = await auth_service.login("alice", "password123")

        auth_service.logout(session.session_id)
        assert auth_service.validate_session(session.session_id) is None

    def test_logout_unknown_session_is_safe(self, auth_service):
        auth_service.logout("nonexistent")  # should not raise


class TestRegisterConcurrentRace:
    """Tests for the race condition where get_by_username returns None but create_user fails."""

    async def test_register_handles_repo_valueerror(self, auth_service):
        """If create_user raises ValueError (concurrent duplicate), AuthError is raised."""
        error = ValueError("Username already taken")
        with (
            patch.object(auth_service._user_repo, "create_user", new_callable=AsyncMock, side_effect=error),
            patch.object(auth_service._user_repo, "get_by_username", new_callable=AsyncMock, return_value=None),
            pytest.raises(AuthError, match="already taken"),
        ):
            await auth_service.register("raceuser", "password123")


class TestValidateApiKey:
    async def _create_bot(self, user_repo, username: str = "ValidBot") -> tuple[User, str]:
        """Create a bot user directly via the repository. Return (User, raw_api_key)."""
        raw_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        bot = User(
            user_id=f"bot-{username.lower()}",
            username=username,
            password_hash="!",
            account_type=AccountType.BOT,
            api_key_hash=api_key_hash,
        )
        await user_repo.create_user(bot)
        return bot, raw_key

    async def test_valid_key_returns_bot_user(self, auth_service, user_repo):
        bot, raw_key = await self._create_bot(user_repo)

        result = await auth_service.validate_api_key(raw_key)
        assert result is not None
        assert result.user_id == bot.user_id
        assert result.account_type == AccountType.BOT

    async def test_invalid_key_returns_none(self, auth_service):
        result = await auth_service.validate_api_key("totally-bogus-key")
        assert result is None

    async def test_wrong_key_returns_none(self, auth_service, user_repo):
        await self._create_bot(user_repo, username="KeyBot")

        result = await auth_service.validate_api_key("wrong-key-value")
        assert result is None


class TestSessionStoreRequired:
    async def test_login_without_session_store_raises(self, user_repo):
        svc = AuthService(user_repo)
        await svc.register("alice", "password123")
        with pytest.raises(RuntimeError, match="session_store is required"):
            await svc.login("alice", "password123")
