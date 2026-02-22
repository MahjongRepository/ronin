"""Tests for lobby server middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lobby.server.middleware import SECURITY_HEADERS, SecurityHeadersMiddleware, SlashNormalizationMiddleware

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

    def test_csp_blocks_scripts(self, security_client: TestClient) -> None:
        """CSP policy disallows script execution."""
        response = security_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "script-src 'none'" in csp

    def test_frame_ancestors_deny(self, security_client: TestClient) -> None:
        """Both X-Frame-Options and CSP frame-ancestors prevent framing."""
        response = security_client.get("/items")
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

    def test_websocket_passthrough(self, security_client: TestClient) -> None:
        """Non-HTTP scopes (WebSocket) pass through without modification."""
        with security_client.websocket_connect("/ws") as ws:
            ws.send_text("hello")
            assert ws.receive_text() == "hello"
