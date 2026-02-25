"""Tests for lobby server middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lobby.server.middleware import (
    SECURITY_HEADERS,
    SecurityHeadersMiddleware,
    SlashNormalizationMiddleware,
)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket


async def _echo_path(request: Request) -> JSONResponse:
    return JSONResponse({"path": request.url.path})


async def _ws_echo(websocket: WebSocket) -> None:
    await websocket.accept()
    data = await websocket.receive_text()
    await websocket.send_text(data)
    await websocket.close()


def _make_slash_app() -> Starlette:
    app = Starlette(
        routes=[Route("/items", _echo_path, methods=["GET"])],
    )
    app.add_middleware(SlashNormalizationMiddleware)
    return app


def _make_security_headers_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/items", _echo_path, methods=["GET"]),
            Route("/game", _echo_path, methods=["GET"]),
            Route("/game-assets/test.js", _echo_path, methods=["GET"]),
            WebSocketRoute("/ws", _ws_echo),
        ],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    return app


@pytest.fixture
def slash_client() -> TestClient:
    return TestClient(_make_slash_app())


@pytest.fixture
def security_client() -> TestClient:
    return TestClient(_make_security_headers_app())


class TestSlashNormalizationMiddleware:
    def test_trailing_slash_stripped(self, slash_client: TestClient) -> None:
        response = slash_client.get("/items/")
        assert response.status_code == 200
        assert response.json() == {"path": "/items"}

    def test_no_trailing_slash_unchanged(self, slash_client: TestClient) -> None:
        response = slash_client.get("/items")
        assert response.status_code == 200
        assert response.json() == {"path": "/items"}

    def test_root_path_preserved(self, slash_client: TestClient) -> None:
        """The root path ``/`` must not be stripped to an empty string."""
        response = slash_client.get("/")
        # Root doesn't match /items, so 404 is expected — but path should stay "/"
        assert response.status_code == 404


class TestSecurityHeadersMiddleware:
    def test_headers_present_on_success(self, security_client: TestClient) -> None:
        response = security_client.get("/items")
        assert response.status_code == 200
        for name, value in SECURITY_HEADERS:
            assert response.headers[name.decode()] == value.decode()

    def test_headers_present_on_404(self, security_client: TestClient) -> None:
        """Security headers are added even to error responses."""
        response = security_client.get("/nonexistent")
        assert response.status_code == 404
        for name, value in SECURITY_HEADERS:
            assert response.headers[name.decode()] == value.decode()

    def test_websocket_passthrough(self, security_client: TestClient) -> None:
        """Non-HTTP scopes (WebSocket) pass through without modification."""
        with security_client.websocket_connect("/ws") as ws:
            ws.send_text("hello")
            assert ws.receive_text() == "hello"

    def test_game_route_allows_scripts(self, security_client: TestClient) -> None:
        """Game page CSP allows script execution."""
        response = security_client.get("/game")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "script-src 'none'" not in csp

    def test_game_route_allows_websocket(self, security_client: TestClient) -> None:
        """Game page CSP allows WebSocket connections."""
        response = security_client.get("/game")
        csp = response.headers["content-security-policy"]
        assert "connect-src 'self' ws: wss:" in csp

    def test_game_assets_route_allows_scripts(self, security_client: TestClient) -> None:
        """Game asset paths also get the game CSP."""
        response = security_client.get("/game-assets/test.js")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp

    def test_non_game_route_blocks_scripts(self, security_client: TestClient) -> None:
        """Non-game routes still block script execution."""
        response = security_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "script-src 'none'" in csp

    def test_game_route_trailing_slash_allows_scripts(self, security_client: TestClient) -> None:
        """Game page with trailing slash still gets the game CSP."""
        response = security_client.get("/game/")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "script-src 'none'" not in csp


def _make_trusted_host_app(allowed_hosts: list[str]) -> Starlette:
    app = Starlette(routes=[Route("/items", _echo_path, methods=["GET"])])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    return app


class TestTrustedHostMiddleware:
    def test_allowed_host_passes(self) -> None:
        client = TestClient(_make_trusted_host_app(["testserver"]))
        response = client.get("/items")
        assert response.status_code == 200

    def test_disallowed_host_returns_400(self) -> None:
        client = TestClient(_make_trusted_host_app(["example.com"]))
        response = client.get("/items")
        assert response.status_code == 400

    def test_wildcard_subdomain_matching(self) -> None:
        client = TestClient(
            _make_trusted_host_app(["*.local"]),
            headers={"host": "myapp.local"},
        )
        response = client.get("/items")
        assert response.status_code == 200

    def test_wildcard_subdomain_rejects_non_matching(self) -> None:
        client = TestClient(
            _make_trusted_host_app(["*.local"]),
        )
        # TestClient default host is "testserver"
        response = client.get("/items")
        assert response.status_code == 400
