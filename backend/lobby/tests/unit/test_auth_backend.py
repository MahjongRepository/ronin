from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.authentication import AuthCredentials

from lobby.auth.backend import SessionOrApiKeyBackend
from lobby.auth.models import AuthenticatedPlayer
from shared.auth.session_store import AuthSessionStore
from shared.dal.models import AccountType, Player

if TYPE_CHECKING:
    from shared.auth.models import AuthSession


@pytest.fixture
def session_store() -> AuthSessionStore:
    return AuthSessionStore()


@pytest.fixture
def auth_service(session_store: AuthSessionStore) -> MagicMock:
    svc = MagicMock()
    svc.validate_session = session_store.get_session
    svc.validate_api_key = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def backend(auth_service: MagicMock) -> SessionOrApiKeyBackend:
    return SessionOrApiKeyBackend(auth_service)


@pytest.fixture
def valid_session(session_store: AuthSessionStore) -> AuthSession:
    return session_store.create_session(user_id="user-1", username="testuser")


def _bot_player(user_id: str = "bot-1", username: str = "TestBot") -> Player:
    raw_key = "test-api-key"
    return Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
    )


def _human_player_with_key(user_id: str = "human-1", username: str = "Sneaky") -> Player:
    return Player(
        user_id=user_id,
        username=username,
        password_hash="$2b$12$fakehash",
        account_type=AccountType.HUMAN,
        api_key_hash=hashlib.sha256(b"sneaky-key").hexdigest(),
    )


class TestSessionCookieAuth:
    async def test_session_cookie_auth__when_cookie_valid__should_return_authenticated_tuple(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ):
        conn = MagicMock()
        conn.cookies = {"session_id": valid_session.session_id}
        conn.query_params = {}
        conn.headers = {}

        result = await backend.authenticate(conn)
        assert result is not None
        credentials, user = result
        assert isinstance(credentials, AuthCredentials)
        assert "authenticated" in credentials.scopes
        assert isinstance(user, AuthenticatedPlayer)
        assert user.username == "testuser"
        assert user.user_id == "user-1"

    async def test_session_cookie_auth__when_websocket_with_query_param__should_authenticate(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ):
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {"session_id": valid_session.session_id}
        conn.headers = {}
        conn.scope = {"type": "websocket"}

        result = await backend.authenticate(conn)
        assert result is not None
        credentials, user = result
        assert isinstance(credentials, AuthCredentials)
        assert "authenticated" in credentials.scopes
        assert isinstance(user, AuthenticatedPlayer)
        assert user.username == "testuser"

    async def test_session_cookie_auth__when_http_with_query_param__should_ignore_it(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ):
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {"session_id": valid_session.session_id}
        conn.headers = {}
        conn.scope = {"type": "http"}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_session_cookie_auth__when_cookie_and_query_param__should_prefer_cookie(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
        session_store: AuthSessionStore,
    ):
        other_session = session_store.create_session(user_id="user-other", username="otheruser")

        conn = MagicMock()
        conn.cookies = {"session_id": valid_session.session_id}
        conn.query_params = {"session_id": other_session.session_id}
        conn.headers = {}
        conn.scope = {"type": "websocket"}

        result = await backend.authenticate(conn)
        assert result is not None
        _, user = result
        assert user.username == "testuser"  # from cookie, not query param

    async def test_session_cookie_auth__when_cookie_missing__should_return_none(
        self,
        backend: SessionOrApiKeyBackend,
    ):
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {}
        conn.scope = {"type": "http"}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_session_cookie_auth__when_session_id_invalid__should_return_none(
        self,
        backend: SessionOrApiKeyBackend,
    ):
        conn = MagicMock()
        conn.cookies = {"session_id": "nonexistent-session-id"}
        conn.query_params = {}
        conn.headers = {}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_session_cookie_auth__when_session_expired__should_return_none(
        self,
        backend: SessionOrApiKeyBackend,
        session_store: AuthSessionStore,
    ):
        session = session_store.create_session(user_id="user-2", username="expired_user", ttl_seconds=0)
        session.expires_at = time.time() - 1

        conn = MagicMock()
        conn.cookies = {"session_id": session.session_id}
        conn.query_params = {}
        conn.headers = {}

        result = await backend.authenticate(conn)
        assert result is None


class TestApiKeyAuth:
    async def test_api_key_auth__when_bot_key_valid__should_return_authenticated_tuple(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
    ):
        bot = _bot_player()
        auth_service.validate_api_key.return_value = bot

        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": "test-api-key"}

        result = await backend.authenticate(conn)
        assert result is not None
        credentials, user = result
        assert isinstance(credentials, AuthCredentials)
        assert "authenticated" in credentials.scopes
        assert isinstance(user, AuthenticatedPlayer)
        assert user.username == "TestBot"
        assert user.user_id == "bot-1"

    async def test_api_key_auth__when_key_invalid__should_return_none(
        self,
        backend: SessionOrApiKeyBackend,
    ):
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": "bogus-key"}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_api_key_auth__when_key_belongs_to_human_account__should_return_none(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
    ):
        human = _human_player_with_key()
        auth_service.validate_api_key.return_value = human

        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": "sneaky-key"}

        result = await backend.authenticate(conn)
        assert result is None


class TestAccountTypePropagation:
    async def test_account_type__when_session_auth_human__should_be_human(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ):
        conn = MagicMock()
        conn.cookies = {"session_id": valid_session.session_id}
        conn.query_params = {}
        conn.headers = {}
        conn.scope = {"type": "http"}

        result = await backend.authenticate(conn)
        assert result is not None
        _, user = result
        assert user.account_type == AccountType.HUMAN

    async def test_account_type__when_session_auth_bot__should_be_bot(
        self,
        backend: SessionOrApiKeyBackend,
        session_store: AuthSessionStore,
    ):
        bot_session = session_store.create_session(user_id="bot-1", username="TestBot", account_type=AccountType.BOT)

        conn = MagicMock()
        conn.cookies = {"session_id": bot_session.session_id}
        conn.query_params = {}
        conn.headers = {}
        conn.scope = {"type": "http"}

        result = await backend.authenticate(conn)
        assert result is not None
        _, user = result
        assert user.account_type == AccountType.BOT

    async def test_account_type__when_api_key_auth_bot__should_be_bot(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
    ):
        bot = _bot_player()
        auth_service.validate_api_key.return_value = bot

        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": "test-api-key"}
        conn.scope = {"type": "http"}

        result = await backend.authenticate(conn)
        assert result is not None
        _, user = result
        assert user.account_type == AccountType.BOT


class TestSessionTakesPrecedenceOverApiKey:
    async def test_session_cookie_auth__when_api_key_also_present__should_use_session(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ):
        bot = _bot_player()
        auth_service.validate_api_key.return_value = bot

        conn = MagicMock()
        conn.cookies = {"session_id": valid_session.session_id}
        conn.query_params = {}
        conn.headers = {"x-api-key": "test-api-key"}

        result = await backend.authenticate(conn)
        assert result is not None
        _, user = result
        assert user.username == "testuser"  # from session, not bot
        auth_service.validate_api_key.assert_not_called()
