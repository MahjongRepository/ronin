"""ASGI middleware for the lobby server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Headers added to every HTTP response to mitigate common web vulnerabilities.
_FONTS_STYLE_SRC = "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
_FONTS_FONT_SRC = "font-src 'self' https://fonts.gstatic.com; "

_LOBBY_CSP = (
    "default-src 'self'; "
    "script-src 'none'; " + _FONTS_STYLE_SRC + _FONTS_FONT_SRC + "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

# Room pages need scripts and same-origin WebSocket connections.
_ROOM_CSP = (
    "default-src 'self'; "
    "script-src 'self'; " + _FONTS_STYLE_SRC + _FONTS_FONT_SRC + "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

# Game pages need scripts and WebSocket connections to external game servers.
_GAME_CSP = (
    "default-src 'self'; "
    "script-src 'self'; " + _FONTS_STYLE_SRC + _FONTS_FONT_SRC + "connect-src 'self' ws: wss:; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

_COMMON_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
]

SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    *_COMMON_HEADERS,
    (b"content-security-policy", _LOBBY_CSP.encode()),
]

ROOM_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    *_COMMON_HEADERS,
    (b"content-security-policy", _ROOM_CSP.encode()),
]

GAME_SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    *_COMMON_HEADERS,
    (b"content-security-policy", _GAME_CSP.encode()),
]


def _get_csp_headers(path: str) -> list[tuple[bytes, bytes]]:
    """Select the appropriate CSP headers based on the request path.

    Trailing slashes are stripped before comparison so that the CSP selection
    is consistent regardless of whether ``SlashNormalizationMiddleware`` has
    already run.
    """
    normalized = path.rstrip("/") or "/"
    if normalized == "/game" or path.startswith("/game-assets/"):
        return GAME_SECURITY_HEADERS
    if normalized.startswith("/rooms/"):
        return ROOM_SECURITY_HEADERS
    return SECURITY_HEADERS


class SecurityHeadersMiddleware:
    """Inject standard security headers into every HTTP response.

    Game paths (/game, /game-assets/) get a permissive CSP that allows scripts
    and WebSocket connections. All other paths block scripts entirely.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extra_headers = _get_csp_headers(scope["path"])

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
