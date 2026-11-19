from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from lobby.views.error_pages import validate_csrf
from shared.auth.service import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SESSION_MAX_AGE_SECONDS,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from shared.auth.settings import AuthSettings

GUEST_LOGIN_BURST = 10
GUEST_LOGIN_REFILL_PER_SECOND = 1 / 360

ACCOUNT_RULES = {
    "username_min_length": USERNAME_MIN_LENGTH,
    "username_max_length": USERNAME_MAX_LENGTH,
    "password_min_length": PASSWORD_MIN_LENGTH,
    "password_max_length": PASSWORD_MAX_LENGTH,
}


def parse_next_path(value: object) -> str | None:
    """
    Return ``value`` when it is a path on this site, otherwise None.

    Browsers read ``//host`` and ``/\\host`` as another host and drop tabs and newlines inside a URL, so a path with a
    backslash or a control character is refused too.
    """
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        return None

    if "\\" in value or not value.isprintable():
        return None

    return value


def set_session_cookie(response: Response, *, token: str, auth_settings: AuthSettings) -> None:
    """
    Set the session cookie a login, a registration or a guest login hands the browser.
    """
    response.set_cookie(
        key="session_id",
        value=token,
        httponly=True,
        samesite="lax",
        secure=auth_settings.cookie_secure,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
    )


async def logout(request: Request) -> Response:
    """POST /logout - clear session, redirect to login."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    auth_service = request.app.state.auth_service
    session_id = request.cookies.get("session_id")
    if session_id:
        await auth_service.logout(session_id)

    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(key="session_id", path="/")
    return response
