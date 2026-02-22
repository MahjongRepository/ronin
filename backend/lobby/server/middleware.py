"""ASGI middleware for the lobby server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Headers added to every HTTP response to mitigate common web vulnerabilities.
_CSP = (
    "default-src 'self'; "
    "script-src 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", _CSP.encode()),
]


class SecurityHeadersMiddleware:
    """Inject standard security headers into every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(SECURITY_HEADERS)
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
