"""CSRF protection helpers using the double-submit cookie pattern.

Provides token generation, cookie management, and validation for
state-changing HTML form routes. Bot API routes (JSON + API key)
are exempt since they don't use cookies for authentication.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from starlette.responses import PlainTextResponse

if TYPE_CHECKING:
    from starlette.datastructures import FormData
    from starlette.requests import Request
    from starlette.responses import Response

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"


def get_or_create_csrf_token(request: Request) -> tuple[str, bool]:
    """Return the CSRF token from the cookie, or generate a new one.

    Returns (token, is_new) where is_new indicates a cookie must be set.
    """
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if token:
        return token, False
    return secrets.token_urlsafe(32), True


def set_csrf_cookie(response: Response, token: str, *, cookie_secure: bool) -> None:
    """Set the CSRF token cookie on the response."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=cookie_secure,
        path="/",
    )


def validate_csrf(request: Request, form_data: FormData) -> PlainTextResponse | None:
    """Check that the form CSRF token matches the cookie token.

    Returns a 403 response on failure, or None if the token is valid.
    """
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token:
        return PlainTextResponse("CSRF validation failed", status_code=403)

    form_token = form_data.get(CSRF_FORM_FIELD)
    if not form_token or not isinstance(form_token, str):
        return PlainTextResponse("CSRF validation failed", status_code=403)

    if not secrets.compare_digest(cookie_token, form_token):
        return PlainTextResponse("CSRF validation failed", status_code=403)

    return None
