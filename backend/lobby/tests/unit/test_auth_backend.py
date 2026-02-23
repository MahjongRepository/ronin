"""Tests for the SessionOrApiKeyBackend authentication backend."""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.authentication import AuthCredentials

from lobby.auth.backend import SessionOrApiKeyBackend
from lobby.auth.models import AuthenticatedPlayer
from shared.auth.models import AccountType, Player
from shared.auth.session_store import AuthSessionStore

if TYPE_CHECKING:
    from shared.auth.models import AuthSession


@pytest.fixture
def session_store() -> AuthSessionStore:
    return AuthSessionStore()


@pytest.fixture
def auth_service(session_store: AuthSessionStore) -> MagicMock:
    """Mock auth service that delegates validate_session to a real session store."""
    svc = MagicMock()
    svc.validate_session = session_store.get_session
    svc.validate_api_key = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def backend(auth_service: MagicMock) -> SessionOrApiKeyBackend:
    return SessionOrApiKeyBackend(auth_service)


@pytest.fixture
def valid_session(session_store: AuthSessionStore) -> AuthSession:
    return session_store.create_session("user-1", "testuser")


def _bot_player(user_id: str = "bot-1", username: str = "TestBot") -> Player:
    """Create a bot Player for testing."""
    raw_key = "test-api-key"
    return Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
    )


def _human_player_with_key(user_id: str = "human-1", username: str = "Sneaky") -> Player:
    """Create a human Player with an api_key_hash (defense-in-depth test)."""
    return Player(
        user_id=user_id,
        username=username,
        password_hash="$2b$12$fakehash",
        account_type=AccountType.HUMAN,
        api_key_hash=hashlib.sha256(b"sneaky-key").hexdigest(),
    )


class TestSessionCookieAuth:
    async def test_valid_cookie_returns_authenticated_tuple(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ) -> None:
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

    async def test_query_param_session_id_returns_authenticated_tuple(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ) -> None:
        """WebSocket clients pass session_id as a query parameter."""
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {"session_id": valid_session.session_id}
        conn.headers = {}

        result = await backend.authenticate(conn)

        assert result is not None
        credentials, user = result
        assert isinstance(credentials, AuthCredentials)
        assert "authenticated" in credentials.scopes
        assert isinstance(user, AuthenticatedPlayer)
        assert user.username == "testuser"

    async def test_cookie_takes_precedence_over_query_param(
        self,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
        session_store: AuthSessionStore,
    ) -> None:
        other_session = session_store.create_session("user-other", "otheruser")
        conn = MagicMock()
        conn.cookies = {"session_id": valid_session.session_id}
        conn.query_params = {"session_id": other_session.session_id}
        conn.headers = {}

        result = await backend.authenticate(conn)

        assert result is not None
        _, user = result
        assert user.username == "testuser"  # from cookie, not query param

    async def test_missing_cookie_returns_none(
        self,
        backend: SessionOrApiKeyBackend,
    ) -> None:
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_invalid_session_id_returns_none(
        self,
        backend: SessionOrApiKeyBackend,
    ) -> None:
        conn = MagicMock()
        conn.cookies = {"session_id": "nonexistent-session-id"}
        conn.query_params = {}
        conn.headers = {}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_expired_session_returns_none(
        self,
        backend: SessionOrApiKeyBackend,
        session_store: AuthSessionStore,
    ) -> None:
        session = session_store.create_session("user-2", "expired_user", ttl_seconds=0)
        session.expires_at = time.time() - 1

        conn = MagicMock()
        conn.cookies = {"session_id": session.session_id}
        conn.query_params = {}
        conn.headers = {}

        result = await backend.authenticate(conn)
        assert result is None


class TestApiKeyAuth:
    async def test_valid_bot_api_key_returns_authenticated_tuple(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
    ) -> None:
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

    async def test_invalid_api_key_returns_none(
        self,
        backend: SessionOrApiKeyBackend,
    ) -> None:
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": "bogus-key"}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_human_account_api_key_returns_none(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
    ) -> None:
        """Defense-in-depth: human accounts with an api_key_hash are rejected."""
        human = _human_player_with_key()
        auth_service.validate_api_key.return_value = human

        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": "sneaky-key"}

        result = await backend.authenticate(conn)
        assert result is None

    async def test_empty_api_key_header_returns_none(
        self,
        backend: SessionOrApiKeyBackend,
    ) -> None:
        conn = MagicMock()
        conn.cookies = {}
        conn.query_params = {}
        conn.headers = {"x-api-key": ""}

        result = await backend.authenticate(conn)
        assert result is None


class TestSessionTakesPrecedenceOverApiKey:
    async def test_valid_session_used_even_when_api_key_present(
        self,
        auth_service: MagicMock,
        backend: SessionOrApiKeyBackend,
        valid_session: AuthSession,
    ) -> None:
        """Session cookie takes precedence; API key is not checked."""
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
