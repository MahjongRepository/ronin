"""Tests for lobby server middleware."""

from __future__ import annotations

import re
from pathlib import Path
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


def _make_security_headers_app(vite_dev_url: str = "") -> Starlette:
    app = Starlette(
        routes=[
            Route("/items", _echo_path, methods=["GET"]),
            Route("/play/{game_id}", _echo_path, methods=["GET"]),
            Route("/game-assets/test.js", _echo_path, methods=["GET"]),
            Route("/rooms/test-room", _echo_path, methods=["GET"]),
            WebSocketRoute("/ws", _ws_echo),
        ],
    )
    app.add_middleware(SecurityHeadersMiddleware, vite_dev_url=vite_dev_url)
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

    def test_game_route_allows_same_origin_scripts(self, security_client: TestClient) -> None:
        """Game page CSP allows same-origin script execution (not inline)."""
        response = security_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "script-src 'none'" not in csp

    def test_game_route_allows_websocket(self, security_client: TestClient) -> None:
        """Game page CSP allows WebSocket connections."""
        response = security_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "connect-src 'self' ws: wss:" in csp

    def test_game_assets_route_allows_scripts(self, security_client: TestClient) -> None:
        """Game asset paths also get the game CSP."""
        response = security_client.get("/game-assets/test.js")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp

    def test_lobby_allows_scripts(self, security_client: TestClient) -> None:
        """Lobby pages allow scripts (lobby JS loads on all pages)."""
        response = security_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp

    def test_room_same_csp_as_lobby(self, security_client: TestClient) -> None:
        """Room pages get the same CSP as lobby pages."""
        lobby_csp = security_client.get("/items").headers["content-security-policy"]
        room_csp = security_client.get("/rooms/test-room").headers["content-security-policy"]
        assert lobby_csp == room_csp

    def test_game_route_trailing_slash_allows_scripts(self, security_client: TestClient) -> None:
        """Game page with trailing slash still gets the game CSP."""
        response = security_client.get("/play/test-game/")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "script-src 'none'" not in csp


class TestSecurityHeadersMiddlewareViteDev:
    @pytest.fixture
    def vite_client(self) -> TestClient:
        return TestClient(_make_security_headers_app(vite_dev_url="http://localhost:5173"))

    def test_lobby_allows_vite_scripts_in_dev(self, vite_client: TestClient) -> None:
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "http://localhost:5173" in csp
        assert "script-src 'self' http://localhost:5173" in csp

    def test_lobby_allows_vite_ws_in_dev(self, vite_client: TestClient) -> None:
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "ws://localhost:5173" in csp

    def test_lobby_allows_vite_styles_in_dev(self, vite_client: TestClient) -> None:
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com http://localhost:5173" in csp

    def test_lobby_allows_vite_images_in_dev(self, vite_client: TestClient) -> None:
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "img-src 'self' http://localhost:5173" in csp

    def test_game_allows_vite_scripts_in_dev(self, vite_client: TestClient) -> None:
        response = vite_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "http://localhost:5173" in csp

    def test_game_allows_vite_ws_in_dev(self, vite_client: TestClient) -> None:
        response = vite_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "ws://localhost:5173" in csp

    def test_https_vite_dev_url_uses_wss(self) -> None:
        """HTTPS Vite dev URL produces wss:// WebSocket origin in CSP."""
        client = TestClient(_make_security_headers_app(vite_dev_url="https://localhost:5173"))
        response = client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "wss://localhost:5173" in csp
        assert "ws://localhost:5173" not in csp


# Regex matching <script> tags that lack a src attribute (inline scripts).
_INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc\b)[^>]*>", re.IGNORECASE)
# Regex matching inline event-handler attributes (onclick, onerror, etc.).
# Uses an explicit list of DOM event handler names to avoid false positives
# on non-handler attributes that start with "on" (e.g. "one=", "online=").
_INLINE_HANDLER_RE = re.compile(
    r"\bon(?:abort|auxclick|blur|cancel|change|click|close|contextmenu|copy|cut|"
    r"dblclick|drag|dragend|dragenter|dragleave|dragover|dragstart|drop|"
    r"error|focus|focusin|focusout|input|invalid|keydown|keypress|keyup|"
    r"load|mousedown|mouseenter|mouseleave|mousemove|mouseout|mouseover|mouseup|"
    r"paste|pointerdown|pointerup|reset|resize|scroll|select|submit|"
    r"touchstart|touchend|touchmove|unload|wheel)\s*=",
    re.IGNORECASE,
)

# Templates served with script-src 'self' (game and room pages).
# These must not contain inline scripts or event handlers.
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "views" / "templates"
_SCRIPT_SELF_TEMPLATES = ["base.html", "play.html", "room.html"]


class TestCSPCompliance:
    @pytest.mark.parametrize("template_name", _SCRIPT_SELF_TEMPLATES)
    def test_no_inline_scripts_in_self_csp_templates(self, template_name: str) -> None:
        """Templates served with script-src 'self' must not contain inline scripts."""
        content = (_TEMPLATES_DIR / template_name).read_text()
        matches = _INLINE_SCRIPT_RE.findall(content)
        assert matches == [], (
            f"{template_name} contains inline <script> tags incompatible with script-src 'self': {matches}"
        )

    @pytest.mark.parametrize("template_name", _SCRIPT_SELF_TEMPLATES)
    def test_no_inline_event_handlers_in_self_csp_templates(self, template_name: str) -> None:
        """Templates served with script-src 'self' must not use inline event handlers."""
        content = (_TEMPLATES_DIR / template_name).read_text()
        matches = _INLINE_HANDLER_RE.findall(content)
        assert matches == [], (
            f"{template_name} contains inline event handlers incompatible with script-src 'self': {matches}"
        )


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
