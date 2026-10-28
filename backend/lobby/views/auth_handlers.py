from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from starlette.responses import RedirectResponse, Response

from lobby.auth.csrf import is_csrf_valid
from lobby.views.assets import render_page
from lobby.views.error_pages import validate_csrf
from shared.auth.service import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    USERNAME_PATTERN,
    AuthError,
)
from shared.auth.session_store import DEFAULT_SESSION_TTL_SECONDS

if TYPE_CHECKING:
    from starlette.datastructures import FormData
    from starlette.requests import Request

    from shared.auth.models import AuthSession
    from shared.auth.settings import AuthSettings

SESSION_EXPIRED_ERROR = "Your session expired. Please try again."

_ACCOUNT_RULES = {
    "username_min_length": USERNAME_MIN_LENGTH,
    "username_max_length": USERNAME_MAX_LENGTH,
    "username_pattern": USERNAME_PATTERN.pattern,
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


def _redirect_with_session_cookie(
    *, session: AuthSession, auth_settings: AuthSettings, next_path: str | None
) -> Response:
    """
    Redirect to ``next_path`` (the lobby when there is none) and set the session cookie.
    """
    response = RedirectResponse(next_path or "/", status_code=303)
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


def _render_auth_form(
    request: Request,
    *,
    template_name: str,
    form: FormData | None = None,
    error: str | None = None,
    invalid_field: str | None = None,
) -> Response:
    """
    Render the login or register form, keeping the submitted username (never a password) and the page to return to.

    The username goes under ``form_username``: ``username`` is the logged-in user the navigation shows. The return page
    comes from the submitted form, or from the ``next`` query parameter the login redirect adds.
    """
    submitted = form.get("username", "") if form is not None else ""
    next_path = parse_next_path(form.get("next") if form is not None else request.query_params.get("next"))
    context: dict[str, object] = {
        **_ACCOUNT_RULES,
        "error": error,
        "invalid_field": invalid_field,
        "form_username": submitted if isinstance(submitted, str) else "",
        "next_path": next_path,
        "next_query": f"?{urlencode({'next': next_path})}" if next_path else "",
    }
    return render_page(request, template_name=template_name, context=context)


def _render_stale_auth_form(request: Request, *, template_name: str, form: FormData) -> Response:
    """
    Answer a login or register post whose CSRF check failed with its form again (403), under the cookie's token.

    A browser that has lost its cookie gets a new one with the form, unless the post came from another site.
    """
    response = _render_auth_form(request, template_name=template_name, form=form, error=SESSION_EXPIRED_ERROR)
    response.status_code = HTTPStatus.FORBIDDEN
    return response


async def login_page(request: Request) -> Response:
    """GET /login - render login form with CSRF token."""
    return _render_auth_form(request, template_name="login.html")


async def login(request: Request) -> Response:
    """POST /login - validate credentials, set session cookie, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    form = await request.form()

    if not is_csrf_valid(request, form):
        return _render_stale_auth_form(request, template_name="login.html", form=form)

    username = form.get("username", "")
    password = form.get("password", "")

    try:
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        return _render_auth_form(request, template_name="login.html", form=form, error=str(e))

    return _redirect_with_session_cookie(
        session=session, auth_settings=auth_settings, next_path=parse_next_path(form.get("next"))
    )


async def guest_login(request: Request) -> Response:
    """POST /guest - start a guest session, set the session cookie, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    form = await request.form()

    if not is_csrf_valid(request, form):
        return _render_stale_auth_form(request, template_name="login.html", form=form)

    next_path = parse_next_path(form.get("next"))
    if request.user.is_authenticated:
        return RedirectResponse(next_path or "/", status_code=303)

    return _redirect_with_session_cookie(
        session=auth_service.login_as_guest(), auth_settings=auth_settings, next_path=next_path
    )


async def register_page(request: Request) -> Response:
    """GET /register - render registration form with CSRF token."""
    return _render_auth_form(request, template_name="register.html")


async def register(request: Request) -> Response:
    """POST /register - create account, auto-login, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    form = await request.form()

    if not is_csrf_valid(request, form):
        return _render_stale_auth_form(request, template_name="register.html", form=form)

    username = form.get("username", "")
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")
    if password != confirm_password:
        return _render_auth_form(
            request,
            template_name="register.html",
            form=form,
            error="Passwords do not match.",
            invalid_field="confirm_password",
        )

    try:
        await auth_service.register(str(username), str(password))
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        return _render_auth_form(request, template_name="register.html", form=form, error=str(e))

    return _redirect_with_session_cookie(
        session=session, auth_settings=auth_settings, next_path=parse_next_path(form.get("next"))
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
        auth_service.logout(session_id)

    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(key="session_id", path="/")
    return response
