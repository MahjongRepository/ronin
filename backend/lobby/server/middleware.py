"""ASGI middleware for the lobby server."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

_FONTS_FONT_SRC = "font-src 'self' https://fonts.gstatic.com; "

_COMMON_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
]


def _build_csp_headers(
    vite_dev_url: str,
) -> tuple[
    list[tuple[bytes, bytes]],  # lobby (default — all non-game pages)
    list[tuple[bytes, bytes]],  # game
]:
    """Build path-specific CSP header sets.

    Two tiers:
    - Lobby (all non-game pages, including rooms): scripts + same-origin connect
    - Game: scripts + external WebSocket connect

    When vite_dev_url is set, both tiers also allow scripts and WebSocket from that origin.
    """
    vite_script = ""
    vite_connect = ""
    vite_style = ""
    vite_img = ""
    if vite_dev_url:
        parsed = urlparse(vite_dev_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_origin = f"{ws_scheme}://{parsed.netloc}"
        vite_script = f" {vite_dev_url}"
        vite_connect = f" {vite_dev_url} {ws_origin}"
        vite_style = f" {vite_dev_url}"
        vite_img = f"img-src 'self' {vite_dev_url}; "

    fonts_style_src = f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com{vite_style}; "

    # Lobby pages (including rooms): scripts + same-origin WS
    lobby_csp = (
        "default-src 'self'; "
        f"script-src 'self'{vite_script}; "
        + fonts_style_src
        + _FONTS_FONT_SRC
        + vite_img
        + f"connect-src 'self'{vite_connect}; "
        + "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )

    # Game pages: scripts + external WS
    game_csp = (
        "default-src 'self'; "
        f"script-src 'self'{vite_script}; "
        + fonts_style_src
        + _FONTS_FONT_SRC
        + vite_img
        + f"connect-src 'self' ws: wss:{vite_connect}; "
        + "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )

    return (
        [*_COMMON_HEADERS, (b"content-security-policy", lobby_csp.encode())],
        [*_COMMON_HEADERS, (b"content-security-policy", game_csp.encode())],
    )


# Module-level default for backward compatibility with tests
SECURITY_HEADERS = _build_csp_headers("")[0]


class SecurityHeadersMiddleware:
    """Inject standard security headers into every HTTP response.

    Game paths (/game, /game-assets/) get a CSP that allows scripts and external WebSocket.
    All other paths (lobby, rooms, auth) get a CSP that allows scripts and same-origin WebSocket.
    """

    def __init__(self, app: ASGIApp, *, vite_dev_url: str = "") -> None:
        self.app = app
        self._lobby_headers, self._game_headers = _build_csp_headers(vite_dev_url)

    def _get_csp_headers(self, path: str) -> list[tuple[bytes, bytes]]:
        normalized = path.rstrip("/") or "/"
        if normalized == "/game" or path.startswith("/game-assets/"):
            return self._game_headers
        return self._lobby_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extra_headers = self._get_csp_headers(scope["path"])

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(extra_headers)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SlashNormalizationMiddleware:
    """Strip trailing slashes so that /path/ is handled the same as /path.

    Without this, Starlette's default ``redirect_slashes=True`` responds
    with a 307 redirect for the trailing-slash variant.  That redirect
    bypasses authentication middleware, which means unauthenticated
    requests to ``/servers/`` would get a redirect instead of a 401.

    Applied as ASGI middleware, it rewrites the path *before* routing,
    eliminating the need for duplicate trailing-slash route definitions.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            if len(path) > 1 and path.endswith("/"):
                scope["path"] = path.rstrip("/")
        await self.app(scope, receive, send)
