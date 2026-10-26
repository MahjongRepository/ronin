from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse, Response

from lobby.auth.csrf import validate_csrf
from lobby.views.assets import render_page
from shared.auth.service import AuthError
from shared.auth.session_store import DEFAULT_SESSION_TTL_SECONDS

if TYPE_CHECKING:
    from starlette.requests import Request

    from shared.auth.models import AuthSession
    from shared.auth.settings import AuthSettings


def _redirect_with_session_cookie(session: AuthSession, auth_settings: AuthSettings) -> Response:
    """
    Redirect to the lobby and set the session cookie.
    """
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        samesite="lax",
        secure=auth_settings.cookie_secure,
        max_age=DEFAULT_SESSION_TTL_SECONDS,
        path="/",
    )
    return response


async def login_page(request: Request) -> Response:
    """GET /login - render login form with CSRF token."""
    return render_page(request, template_name="login.html", context={"error": None})


async def login(request: Request) -> Response:
    """POST /login - validate credentials, set session cookie, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    form = await request.form()

    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    username = form.get("username", "")
    password = form.get("password", "")

    try:
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        return render_page(request, template_name="login.html", context={"error": str(e)})

    return _redirect_with_session_cookie(session, auth_settings)


async def register_page(request: Request) -> Response:
    """GET /register - render registration form with CSRF token."""
    return render_page(request, template_name="register.html", context={"error": None})


async def register(request: Request) -> Response:
    """POST /register - create account, auto-login, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    form = await request.form()

    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    username = form.get("username", "")
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")
    if password != confirm_password:
        return render_page(request, template_name="register.html", context={"error": "Passwords do not match"})

    try:
        await auth_service.register(str(username), str(password))
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        return render_page(request, template_name="register.html", context={"error": str(e)})

    return _redirect_with_session_cookie(session, auth_settings)


async def logout(request: Request) -> Response:
    """POST /logout - clear session, redirect to login."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    auth_service = request.app.state.auth_service
    session_id = request.cookies.get("session_id")
    if session_id:
        auth_service.logout(session_id)

    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(key="session_id", path="/")
    return response
