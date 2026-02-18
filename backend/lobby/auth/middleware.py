"""Cookie-based auth middleware for lobby routes.

HTML routes redirect to /login when unauthenticated.
JSON API routes return 401 with a JSON body.
"""

from http.cookies import CookieError, SimpleCookie
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse, RedirectResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from shared.auth.service import AuthService

UNPROTECTED_PATHS = {"/login", "/register", "/health", "/api/auth/bot", "/api/rooms/create"}

# JSON API paths return 401 instead of redirect to preserve API contract
# for machine clients (game server registry, external tools, tests).
# Exact paths only — HTML form endpoints like /rooms/new and /rooms/{id}/join
# should redirect to /login, not return JSON 401.
JSON_API_PATHS = {"/rooms", "/servers"}


class AuthMiddleware:
    """Check session cookie on protected routes."""

    def __init__(self, app: ASGIApp, auth_service: AuthService) -> None:
        self.app = app
        self._auth_service = auth_service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"].rstrip("/") or "/"

        if path in UNPROTECTED_PATHS or path.startswith("/static"):
            await self.app(scope, receive, send)
            return

        session_id = _get_cookie_from_scope(scope, "session_id")
        session = self._auth_service.validate_session(session_id)

        if session is None:
            if path in JSON_API_PATHS:
                response = JSONResponse({"error": "Authentication required"}, status_code=401)
                await response(scope, receive, send)
                return
            response = RedirectResponse("/login", status_code=303)
            await response(scope, receive, send)
            return

        if "state" not in scope:  # pragma: no cover — Starlette always initializes scope["state"]
            scope["state"] = {}
        scope["state"]["user"] = session
        await self.app(scope, receive, send)


def _get_cookie_from_scope(scope: Scope, name: str) -> str | None:
    """Extract a cookie value from the ASGI scope headers."""
    headers = scope.get("headers", [])
    for header_name, header_value in headers:
        if header_name == b"cookie":
            try:
                cookie = SimpleCookie(header_value.decode("latin-1"))
            except CookieError:
                continue
            morsel = cookie.get(name)
            if morsel is not None:
                return morsel.value
    return None
