"""Tests for the lobby auth middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lobby.auth.middleware import AuthMiddleware
from shared.auth.session_store import AuthSessionStore

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from shared.auth.models import AuthSession


def _make_app(auth_service: MagicMock) -> Starlette:
    """Build a minimal Starlette app with auth middleware for testing."""

    async def index(request: Request) -> PlainTextResponse:
        user = request.state.user
        return PlainTextResponse(f"hello {user.username}")

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def login_page(request: Request) -> PlainTextResponse:
        return PlainTextResponse("login form")

    async def register_page(request: Request) -> PlainTextResponse:
        return PlainTextResponse("register form")

    async def api_rooms(request: Request) -> JSONResponse:
        return JSONResponse({"rooms": []})

    async def api_servers(request: Request) -> JSONResponse:
        return JSONResponse({"servers": []})

    async def bot_auth(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def static_file(request: Request) -> PlainTextResponse:
        return PlainTextResponse("body { }")

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("ok")
        await websocket.close()

    routes = [
        Route("/", index),
        Route("/health", health),
        Route("/login", login_page),
        Route("/register", register_page),
        Route("/rooms", api_rooms),
        Route("/servers", api_servers),
        Route("/api/auth/bot", bot_auth, methods=["POST"]),
        Route("/static/test.css", static_file),
        WebSocketRoute("/ws", ws_endpoint),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(AuthMiddleware, auth_service=auth_service)
    return app


@pytest.fixture
def session_store() -> AuthSessionStore:
    return AuthSessionStore()


@pytest.fixture
def auth_service(session_store: AuthSessionStore) -> MagicMock:
    """Mock auth service that delegates validate_session to a real session store."""
    svc = MagicMock()
    svc.validate_session = session_store.get_session
    return svc


@pytest.fixture
def valid_session(session_store: AuthSessionStore) -> AuthSession:
    return session_store.create_session("user-1", "testuser")


class TestAuthMiddleware:
    def test_unprotected_health_passes_through(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_unprotected_login_passes_through(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/login")
        assert response.status_code == 200
        assert response.text == "login form"

    def test_unprotected_register_passes_through(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/register")
        assert response.status_code == 200
        assert response.text == "register form"

    def test_protected_html_route_redirects_to_login(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_protected_json_api_rooms_returns_401(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/rooms")
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}

    def test_protected_json_api_servers_returns_401(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.get("/servers")
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}

    def test_valid_session_cookie_grants_access(
        self,
        auth_service: MagicMock,
        valid_session: AuthSession,
    ) -> None:
        client = TestClient(_make_app(auth_service))
        client.cookies.set("session_id", valid_session.session_id)
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "hello testuser"

    def test_invalid_session_cookie_redirects(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        client.cookies.set("session_id", "nonexistent-session-id")
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_trailing_slash_normalization(self, auth_service: MagicMock) -> None:
        """Paths with trailing slashes are normalized before matching unprotected set."""
        client = TestClient(_make_app(auth_service))
        response = client.get("/login/")
        assert response.status_code == 200
        assert response.text == "login form"

    def test_unprotected_bot_auth_passes_through(self, auth_service: MagicMock) -> None:
        client = TestClient(_make_app(auth_service))
        response = client.post("/api/auth/bot", json={"api_key": "k", "room_id": "r"})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_static_paths_pass_through(self, auth_service: MagicMock) -> None:
        """Paths under /static/ are unprotected so login/register pages can load assets."""
        client = TestClient(_make_app(auth_service))
        response = client.get("/static/test.css")
        assert response.status_code == 200
        assert response.text == "body { }"

    def test_websocket_passes_through_without_auth(self, auth_service: MagicMock) -> None:
        """Non-HTTP scopes (WebSocket) pass through the middleware without auth checks."""
        client = TestClient(_make_app(auth_service))
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_text()
            assert data == "ok"

    def test_malformed_cookie_header_treated_as_unauthenticated(
        self,
        auth_service: MagicMock,
    ) -> None:
        """A Cookie header that triggers CookieError is treated as no valid cookie."""
        client = TestClient(_make_app(auth_service))
        response = client.get("/", headers={"cookie": "a,b=c"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
