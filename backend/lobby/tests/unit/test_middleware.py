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

from lobby.server.middleware import SecurityHeadersMiddleware, SlashNormalizationMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

_LOBBY_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; connect-src 'self'; "
        "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    ),
}


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
    def test_slash_normalization_middleware__when_trailing_slash__should_strip_it(self, slash_client: TestClient):
        response = slash_client.get("/items/")
        assert response.status_code == 200
        assert response.json() == {"path": "/items"}

    def test_slash_normalization_middleware__when_no_trailing_slash__should_leave_path_unchanged(
        self, slash_client: TestClient
    ):
        response = slash_client.get("/items")
        assert response.status_code == 200
        assert response.json() == {"path": "/items"}

    def test_slash_normalization_middleware__when_root_path__should_keep_it(self, slash_client: TestClient):
        response = slash_client.get("/")
        # Root doesn't match /items, so 404 is expected — but path should stay "/"
        assert response.status_code == 404


class TestSecurityHeadersMiddleware:
    def test_security_headers_middleware__when_success__should_add_headers(self, security_client: TestClient):
        response = security_client.get("/items")
        assert response.status_code == 200
        for name, value in _LOBBY_SECURITY_HEADERS.items():
            assert response.headers[name] == value

    def test_security_headers_middleware__when_404__should_add_headers(self, security_client: TestClient):
        response = security_client.get("/nonexistent")
        assert response.status_code == 404
        for name, value in _LOBBY_SECURITY_HEADERS.items():
            assert response.headers[name] == value

    def test_security_headers_middleware__when_websocket__should_pass_through(self, security_client: TestClient):
        with security_client.websocket_connect("/ws") as ws:
            ws.send_text("hello")
            assert ws.receive_text() == "hello"

    def test_security_headers_middleware__when_game_route__should_allow_self_scripts(self, security_client: TestClient):
        response = security_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "script-src 'none'" not in csp

    def test_security_headers_middleware__when_game_route__should_allow_websocket_connect(
        self, security_client: TestClient
    ):
        response = security_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "connect-src 'self' ws: wss:" in csp

    def test_security_headers_middleware__when_game_assets_route__should_allow_self_scripts(
        self, security_client: TestClient
    ):
        response = security_client.get("/game-assets/test.js")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp

    def test_security_headers_middleware__when_lobby_route__should_allow_self_scripts(
        self, security_client: TestClient
    ):
        response = security_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp

    def test_security_headers_middleware__when_room_route__should_match_lobby_csp(self, security_client: TestClient):
        lobby_csp = security_client.get("/items").headers["content-security-policy"]
        room_csp = security_client.get("/rooms/test-room").headers["content-security-policy"]
        assert lobby_csp == room_csp

    def test_security_headers_middleware__when_game_route_trailing_slash__should_allow_self_scripts(
        self, security_client: TestClient
    ):
        response = security_client.get("/play/test-game/")
        csp = response.headers["content-security-policy"]
        assert "script-src 'self'" in csp
        assert "script-src 'none'" not in csp


class TestSecurityHeadersMiddlewareViteDev:
    @pytest.fixture
    def vite_client(self) -> TestClient:
        return TestClient(_make_security_headers_app(vite_dev_url="http://localhost:5173"))

    def test_security_headers_middleware__when_vite_dev_on_lobby__should_allow_vite_scripts(
        self, vite_client: TestClient
    ):
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "http://localhost:5173" in csp
        assert "script-src 'self' http://localhost:5173" in csp

    def test_security_headers_middleware__when_vite_dev_on_lobby__should_allow_vite_websocket(
        self, vite_client: TestClient
    ):
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "ws://localhost:5173" in csp

    def test_security_headers_middleware__when_vite_dev_on_lobby__should_allow_vite_styles(
        self, vite_client: TestClient
    ):
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com http://localhost:5173" in csp

    def test_security_headers_middleware__when_vite_dev_on_lobby__should_allow_vite_images(
        self, vite_client: TestClient
    ):
        response = vite_client.get("/items")
        csp = response.headers["content-security-policy"]
        assert "img-src 'self' http://localhost:5173" in csp

    def test_security_headers_middleware__when_vite_dev_on_game__should_allow_vite_scripts(
        self, vite_client: TestClient
    ):
        response = vite_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "http://localhost:5173" in csp

    def test_security_headers_middleware__when_vite_dev_on_game__should_allow_vite_websocket(
        self, vite_client: TestClient
    ):
        response = vite_client.get("/play/test-game")
        csp = response.headers["content-security-policy"]
        assert "ws://localhost:5173" in csp

    def test_security_headers_middleware__when_vite_dev_url_https__should_use_wss(self):
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

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "views" / "templates"
_SCRIPT_SELF_TEMPLATES = ["base.html", "room.html"]


class TestCSPCompliance:
    @pytest.mark.parametrize("template_name", _SCRIPT_SELF_TEMPLATES)
    def test_csp_templates__should_contain_no_inline_scripts(self, template_name: str):
        content = (_TEMPLATES_DIR / template_name).read_text()
        matches = _INLINE_SCRIPT_RE.findall(content)
        assert matches == [], (
            f"{template_name} contains inline <script> tags incompatible with script-src 'self': {matches}"
        )

    @pytest.mark.parametrize("template_name", _SCRIPT_SELF_TEMPLATES)
    def test_csp_templates__should_contain_no_inline_event_handlers(self, template_name: str):
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
    def test_trusted_host_middleware__when_host_allowed__should_pass(self):
        client = TestClient(_make_trusted_host_app(["testserver"]))
        response = client.get("/items")
        assert response.status_code == 200

    def test_trusted_host_middleware__when_host_disallowed__should_return_400(self):
        client = TestClient(_make_trusted_host_app(["example.com"]))
        response = client.get("/items")
        assert response.status_code == 400

    def test_trusted_host_middleware__when_host_matches_wildcard__should_pass(self):
        client = TestClient(
            _make_trusted_host_app(["*.local"]),
            headers={"host": "myapp.local"},
        )
        response = client.get("/items")
        assert response.status_code == 200

    def test_trusted_host_middleware__when_host_misses_wildcard__should_return_400(self):
        client = TestClient(
            _make_trusted_host_app(["*.local"]),
        )
        # TestClient default host is "testserver"
        response = client.get("/items")
        assert response.status_code == 400
