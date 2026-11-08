from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from contextlib import closing
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from shared.auth.password import BcryptHasher
from shared.auth.service import GUEST_SESSION_IDLE_SECONDS, AuthError, AuthService
from shared.dal.models import AccountType, AuthSession, Player
from shared.db import Database, SqlitePlayerRepository, SqliteSessionRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


LOGIN_TIME = 1_000_000.0
DAY = 86400


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
async def db(db_path: Path) -> AsyncIterator[Database]:
    database = Database(db_path)
    await database.open()
    yield database
    await database.close()


@pytest.fixture
def player_repo(db: Database) -> SqlitePlayerRepository:
    return SqlitePlayerRepository(db)


@pytest.fixture
def session_repo(db: Database) -> SqliteSessionRepository:
    return SqliteSessionRepository(db)


def _auth_service(db: Database) -> AuthService:
    return AuthService(SqlitePlayerRepository(db), SqliteSessionRepository(db), password_hasher=BcryptHasher(rounds=4))


@pytest.fixture
def auth_service(db: Database) -> AuthService:
    return _auth_service(db)


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
            await auth_service.register("a" * 17, "password123")

    async def test_auth_service_register__when_username_has_special_chars__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="letters, numbers, and underscores"):
            await auth_service.register("alice!", "password123")

    async def test_auth_service_register__when_username_ends_with_newline__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="letters, numbers, and underscores"):
            await auth_service.register("alice\n", "password123")

    @pytest.mark.parametrize(
        "username",
        [
            "ai-bob",
            "AI-bob",
            "ai_bob",
            "Ai_bob",
            "ai\N{EM DASH}bob",
            "ai\N{EN DASH}bob",
            "ai\N{MINUS SIGN}bob",
            "ai\N{KATAKANA-HIRAGANA PROLONGED SOUND MARK}bob",
            "nanashi",
            "NANASHI99",
            "Nanashi_1234",
            "Nanashi-1234",
        ],
    )
    async def test_auth_service_register__when_username_has_reserved_prefix__should_raise_reserved(
        self, auth_service, username
    ):
        with pytest.raises(AuthError, match="are reserved"):
            await auth_service.register(username, "password123")

    @pytest.mark.parametrize("username", ["aiko", "Nanami"])
    async def test_auth_service_register__when_username_only_resembles_reserved__should_create_player(
        self, auth_service, username
    ):
        player = await auth_service.register(username, "password123")
        assert player.username == username

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
        player, raw_api_key = await auth_service.register_bot("ai-mybot")
        assert player.username == "ai-mybot"
        assert player.account_type == AccountType.BOT
        assert player.password_hash == "!"
        assert player.api_key_hash is not None
        assert raw_api_key
        # The raw key hashes to the stored hash
        expected_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
        assert player.api_key_hash == expected_hash

    async def test_auth_service_register_bot__when_name_taken__should_raise(self, auth_service):
        await auth_service.register_bot("ai-uniquebot")

        with pytest.raises(AuthError, match="already taken"):
            await auth_service.register_bot("ai-uniquebot")

    async def test_auth_service_register_bot__when_name_invalid__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="between"):
            await auth_service.register_bot("ab")

    @pytest.mark.parametrize("bot_name", ["MyBot", "AI-bot", "ai_bot", "ai-Bot", "ai-"])
    async def test_auth_service_register_bot__when_name_breaks_the_bot_pattern__should_raise(
        self, auth_service, bot_name
    ):
        with pytest.raises(AuthError, match="must start with 'ai-'"):
            await auth_service.register_bot(bot_name)


class TestIssueBotApiKey:
    async def test_auth_service_issue_bot_api_key__when_bot_exists__should_replace_its_key_on_the_same_account(
        self, auth_service
    ):
        registered, old_key = await auth_service.register_bot("ai-keptbot")

        reissued, new_key = await auth_service.issue_bot_api_key("ai-keptbot")
        assert reissued.user_id == registered.user_id
        assert new_key != old_key
        assert (await auth_service.validate_api_key(new_key)).user_id == registered.user_id
        assert await auth_service.validate_api_key(old_key) is None

    async def test_auth_service_issue_bot_api_key__when_bot_missing__should_register_it(self, auth_service):
        player, raw_api_key = await auth_service.issue_bot_api_key("ai-freshbot")

        assert player.account_type == AccountType.BOT
        assert (await auth_service.validate_api_key(raw_api_key)).user_id == player.user_id

    async def test_auth_service_issue_bot_api_key__when_name_belongs_to_human__should_raise(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="human account"):
            await auth_service.issue_bot_api_key("Alice")

    async def test_auth_service_issue_bot_api_key__when_repo_reports_missing_player__should_raise_auth_error(
        self, auth_service
    ):
        await auth_service.register_bot("ai-racedbot")
        error = ValueError("Player with id 'x' does not exist")

        with (
            patch.object(auth_service._player_repo, "set_api_key_hash", new_callable=AsyncMock, side_effect=error),
            pytest.raises(AuthError, match="does not exist"),
        ):
            await auth_service.issue_bot_api_key("ai-racedbot")


class TestLogin:
    async def test_auth_service_login__when_credentials_valid__should_return_session(self, auth_service):
        await auth_service.register("alice", "password123")

        session, token = await auth_service.login("alice", "password123")
        assert session.username == "alice"
        assert (await auth_service.validate_session(token)).user_id == session.user_id

    async def test_auth_service_login__when_session_created__should_store_the_token_hash_not_the_token(
        self, auth_service, db_path
    ):
        await auth_service.register("alice", "password123")

        _, token = await auth_service.login("alice", "password123")
        with closing(sqlite3.connect(db_path)) as conn:
            stored = conn.execute("SELECT token_hash FROM sessions").fetchall()
        assert stored == [(hashlib.sha256(token.encode()).hexdigest(),)]

    async def test_auth_service_login__when_replacing_an_earlier_token__should_invalidate_it(self, auth_service):
        await auth_service.register("alice", "password123")
        _, earlier_token = await auth_service.login("alice", "password123")

        _, token = await auth_service.login("alice", "password123", replacing=earlier_token)
        assert await auth_service.validate_session(earlier_token) is None
        assert await auth_service.validate_session(token) is not None

    async def test_auth_service_login__when_password_wrong__should_raise(self, auth_service):
        await auth_service.register("alice", "password123")

        with pytest.raises(AuthError, match="Wrong username or password"):
            await auth_service.login("alice", "wrongpassword")

    async def test_auth_service_login__when_player_unknown__should_raise(self, auth_service):
        with pytest.raises(AuthError, match="Wrong username or password"):
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

        with pytest.raises(AuthError, match="Wrong username or password"):
            await auth_service.login("TestBot", "anything1")


class TestLoginAsGuest:
    async def test_auth_service_login_as_guest__when_only_free_name_held_by_expired_session__should_take_it(
        self, auth_service, session_repo, monkeypatch
    ):
        expired_name, *live_names = guest_names = ("Nanashi-1001", "Nanashi-1002", "Nanashi-1003")
        monkeypatch.setattr("shared.auth.service.GUEST_NAMES", guest_names)
        live_until = time.time() + GUEST_SESSION_IDLE_SECONDS
        for name, expires_at in [(expired_name, 1.0), *((name, live_until) for name in live_names)]:
            holder = AuthSession(
                token_hash=f"hash-{name}",
                user_id=f"holder-{name}",
                username=name,
                is_guest=True,
                created_at=0.0,
                expires_at=expires_at,
            )
            await session_repo.create(holder, now=0.0, replacing_token_hash=None)

        session, _ = await auth_service.login_as_guest()
        assert session.username == expired_name
        assert not session.user_id.startswith("holder-")


class TestValidateSession:
    async def test_auth_service_validate_session__when_active__should_return_session(self, auth_service):
        await auth_service.register("alice", "password123")
        _, token = await auth_service.login("alice", "password123")

        result = await auth_service.validate_session(token)
        assert result is not None
        assert result.username == "alice"

    async def test_auth_service_validate_session__when_token_unknown__should_return_none(self, auth_service):
        assert await auth_service.validate_session("nonexistent") is None

    async def test_auth_service_validate_session__when_token_is_none__should_return_none(self, auth_service):
        assert await auth_service.validate_session(None) is None

    async def test_auth_service_validate_session__when_account_used_on_day_20__should_still_validate_on_day_45(
        self, auth_service
    ):
        await auth_service.register("alice", "password123")
        with patch("shared.auth.service.time") as mock_time:
            mock_time.time.return_value = LOGIN_TIME
            _, token = await auth_service.login("alice", "password123")

            mock_time.time.return_value = LOGIN_TIME + 20 * DAY
            assert await auth_service.validate_session(token) is not None

            mock_time.time.return_value = LOGIN_TIME + 45 * DAY
            assert await auth_service.validate_session(token) is not None

            mock_time.time.return_value = LOGIN_TIME + 75 * DAY
            assert await auth_service.validate_session(token) is None

    async def test_auth_service_validate_session__when_used_daily_toward_the_cap__should_reject_at_day_90(
        self, auth_service
    ):
        await auth_service.register("alice", "password123")
        with patch("shared.auth.service.time") as mock_time:
            mock_time.time.return_value = LOGIN_TIME
            _, token = await auth_service.login("alice", "password123")

            for day in [20, 40, *range(59, 90)]:
                mock_time.time.return_value = LOGIN_TIME + day * DAY
                assert await auth_service.validate_session(token) is not None

            mock_time.time.return_value = LOGIN_TIME + 90 * DAY - 1
            assert await auth_service.validate_session(token) is not None

            mock_time.time.return_value = LOGIN_TIME + 90 * DAY
            assert await auth_service.validate_session(token) is None

    async def test_auth_service_validate_session__when_guest_idle_7_days_after_use__should_return_none(
        self, auth_service
    ):
        with patch("shared.auth.service.time") as mock_time:
            mock_time.time.return_value = LOGIN_TIME
            _, token = await auth_service.login_as_guest()

            mock_time.time.return_value = LOGIN_TIME + 6 * DAY
            assert await auth_service.validate_session(token) is not None

            mock_time.time.return_value = LOGIN_TIME + 12 * DAY
            assert await auth_service.validate_session(token) is not None

            mock_time.time.return_value = LOGIN_TIME + 19 * DAY
            assert await auth_service.validate_session(token) is None

    async def test_auth_service_validate_session__when_database_reopened__should_return_session_created_before(
        self, db_path
    ):
        first_db = Database(db_path)
        await first_db.open()
        first_service = _auth_service(first_db)
        await first_service.register("alice", "password123")
        _, token = await first_service.login("alice", "password123")
        await first_db.close()

        reopened_db = Database(db_path)
        await reopened_db.open()
        try:
            result = await _auth_service(reopened_db).validate_session(token)
        finally:
            await reopened_db.close()
        assert result is not None
        assert result.username == "alice"


class TestLogout:
    async def test_auth_service_logout__when_session_exists__should_invalidate_it(self, auth_service):
        await auth_service.register("alice", "password123")
        _, token = await auth_service.login("alice", "password123")

        await auth_service.logout(token)
        assert await auth_service.validate_session(token) is None


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
