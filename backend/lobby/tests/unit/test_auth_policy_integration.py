from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lobby.auth.backend import SessionOrApiKeyBackend
from lobby.auth.policy import collect_protected_api_paths, protected_api, protected_html, public_route
from lobby.server.app import _make_auth_error_handler
from lobby.server.middleware import SlashNormalizationMiddleware
from shared.auth.session_store import AuthSessionStore
from shared.dal.models import AccountType, Player

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from shared.auth.models import AuthSession


def _make_app(auth_service: MagicMock) -> Starlette:
    async def index(request: Request) -> PlainTextResponse:
        return PlainTextResponse(f"hello {request.user.username}")

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def login_page(request: Request) -> PlainTextResponse:
        return PlainTextResponse("login form")

    async def api_rooms(request: Request) -> JSONResponse:
        return JSONResponse({"rooms": []})

    async def api_servers(request: Request) -> JSONResponse:
        return JSONResponse({"servers": []})

    async def bot_auth(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("ok")
        await websocket.close()

    routes = [
        Route("/", protected_html(index), methods=["GET"], name="index"),
        Route("/health", public_route(health), methods=["GET"], name="health"),
        Route("/login", public_route(login_page), methods=["GET"], name="login_page"),
        Route("/rooms", protected_api(api_rooms), methods=["GET"], name="list_rooms"),
        Route("/servers", protected_api(api_servers), methods=["GET"], name="list_servers"),
        Route("/api/auth/bot", public_route(bot_auth), methods=["POST"], name="bot_auth"),
        WebSocketRoute("/ws", ws_endpoint),
    ]

    protected_api_paths = collect_protected_api_paths(routes)
    app = Starlette(
        routes=routes,
        exception_handlers={HTTPException: _make_auth_error_handler(protected_api_paths)},
    )
    app.add_middleware(SlashNormalizationMiddleware)
    app.add_middleware(AuthenticationMiddleware, backend=SessionOrApiKeyBackend(auth_service))
    return app


def _bot_player(user_id: str = "bot-1", username: str = "TestBot") -> Player:
    return Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=hashlib.sha256(b"test-api-key").hexdigest(),
    )


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
def valid_session(session_store: AuthSessionStore) -> AuthSession:
    return session_store.create_session(user_id="user-1", username="testuser")


class TestPublicRoutesPassUnauthenticated:
    def test_auth_policy__when_health_without_session__should_allow(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_auth_policy__when_login_page_without_session__should_allow(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/login")
        assert response.status_code == 200
        assert response.text == "login form"

    def test_auth_policy__when_bot_auth_without_session__should_allow(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.post("/api/auth/bot", json={"api_key": "k"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}


class TestProtectedHtmlRedirectsToLogin:
    def test_auth_policy__when_unauthenticated_html_route__should_redirect_to_login_with_next(
        self, auth_service: MagicMock
    ) -> None:
        client = TestClient(_make_app(auth_service), follow_redirects=False)
        response = client.get("/")
        assert response.status_code == 303
        location = response.headers["location"]
        parsed = urlparse(location)
        assert parsed.path == "/login"
        assert "next" in parse_qs(parsed.query)


class TestProtectedJsonReturns401:
    def test_auth_policy__when_unauthenticated_rooms_api__should_return_401_json(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/rooms")
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}


class TestTrailingSlashReturns401:
    def test_auth_policy__when_rooms_with_trailing_slash_unauthenticated__should_return_401(
        self, auth_service: MagicMock
    ) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/rooms/")
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}


class TestValidSessionGrantsAccess:
    def test_auth_policy__when_valid_session_on_html_route__should_allow(
        self,
        auth_service: MagicMock,
        valid_session: AuthSession,
    ) -> None:
        client = TestClient(_make_app(auth_service))
        client.cookies.set("session_id", valid_session.session_id)
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "hello testuser"

    def test_auth_policy__when_valid_session_on_api_route__should_allow(
        self,
        auth_service: MagicMock,
        valid_session: AuthSession,
    ) -> None:
        client = TestClient(_make_app(auth_service))
        client.cookies.set("session_id", valid_session.session_id)
        response = client.get("/rooms")
        assert response.status_code == 200
        assert response.json() == {"rooms": []}


class TestApiKeyGrantsAccess:
    def test_auth_policy__when_valid_api_key_on_protected_api__should_allow(self, auth_service: MagicMock) -> None:
        bot = _bot_player()
        auth_service.validate_api_key.return_value = bot

        client = TestClient(_make_app(auth_service))
        response = client.get("/rooms", headers={"x-api-key": "test-api-key"})
        assert response.status_code == 200
        assert response.json() == {"rooms": []}

    def test_auth_policy__when_valid_api_key_on_protected_html__should_allow(self, auth_service: MagicMock) -> None:
        bot = _bot_player()
        auth_service.validate_api_key.return_value = bot

        client = TestClient(_make_app(auth_service))
        response = client.get("/", headers={"x-api-key": "test-api-key"})
        assert response.status_code == 200
        assert response.text == "hello TestBot"

    def test_auth_policy__when_invalid_api_key_on_protected_api__should_return_401(
        self, auth_service: MagicMock
    ) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/rooms", headers={"x-api-key": "bogus-key"})
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}

    def test_auth_policy__when_invalid_api_key_on_protected_html__should_redirect(
        self, auth_service: MagicMock
    ) -> None:
        client = TestClient(_make_app(auth_service), follow_redirects=False)
        response = client.get("/", headers={"x-api-key": "bogus-key"})
        assert response.status_code == 303
        parsed = urlparse(response.headers["location"])
        assert parsed.path == "/login"


class TestInvalidCookieTreatedAsUnauthenticated:
    def test_auth_policy__when_session_id_nonexistent__should_redirect(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service), follow_redirects=False)
        client.cookies.set("session_id", "nonexistent-session-id")
        response = client.get("/")
        assert response.status_code == 303
        parsed = urlparse(response.headers["location"])
        assert parsed.path == "/login"

    def test_auth_policy__when_invalid_cookie_on_api__should_return_401(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        client.cookies.set("session_id", "bogus-id")
        response = client.get("/rooms")
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}


class TestWebSocketNonRegressive:
    def test_auth_policy__when_websocket_without_auth__should_connect(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_text()
            assert data == "ok"
