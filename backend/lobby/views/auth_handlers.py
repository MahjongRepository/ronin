"""Auth endpoints: login, register, logout, bot auth, and bot room creation for the lobby."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse, RedirectResponse, Response

from lobby.server.csrf import get_or_create_csrf_token, set_csrf_cookie, validate_csrf
from shared.auth.service import AuthError
from shared.auth.session_store import DEFAULT_SESSION_TTL_SECONDS

if TYPE_CHECKING:
    from starlette.requests import Request

    from shared.auth.models import AuthSession
    from shared.auth.settings import AuthSettings


async def _parse_json_body(request: Request) -> dict | None:
    """Parse JSON body from request. Return None on failure."""
    try:
        body = await request.json()
    except ValueError, json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    return body


def _redirect_with_session_cookie(session: AuthSession, auth_settings: AuthSettings) -> Response:
    """Redirect to the lobby and set the session cookie."""
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
    templates = request.app.state.templates
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"error": None, "csrf_token": csrf_token},
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def login(request: Request) -> Response:
    """POST /login - validate credentials, set session cookie, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    templates = request.app.state.templates
    form = await request.form()

    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    username = form.get("username", "")
    password = form.get("password", "")

    try:
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        csrf_token, _ = get_or_create_csrf_token(request)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": str(e), "csrf_token": csrf_token},
        )

    return _redirect_with_session_cookie(session, auth_settings)


async def register_page(request: Request) -> Response:
    """GET /register - render registration form with CSRF token."""
    templates = request.app.state.templates
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "register.html",
        {"error": None, "csrf_token": csrf_token},
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def register(request: Request) -> Response:
    """POST /register - create account, auto-login, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    templates = request.app.state.templates
    form = await request.form()

    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    username = form.get("username", "")
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")

    if password != confirm_password:
        csrf_token, _ = get_or_create_csrf_token(request)
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Passwords do not match", "csrf_token": csrf_token},
        )

    try:
        await auth_service.register(str(username), str(password))
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        csrf_token, _ = get_or_create_csrf_token(request)
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": str(e), "csrf_token": csrf_token},
        )
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


async def bot_auth(request: Request) -> Response:
    """POST /api/auth/bot {room_id} - create lobby session for bot to join room via WS."""
    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    room_id = body.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        return JSONResponse({"error": "room_id is required as a non-empty string"}, status_code=400)

    room_manager = request.app.state.room_manager
    room = room_manager.get_room(room_id)
    if room is None:
        return JSONResponse({"error": "Room not found"}, status_code=404)

    auth_service = request.app.state.auth_service
    session = auth_service.create_session(
        request.user.user_id,
        request.user.username,
        account_type=request.user.account_type,
    )

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse({"session_id": session.session_id, "room_id": room_id, "ws_url": ws_url})


async def bot_create_room(request: Request) -> Response:
    """POST /api/rooms - create a room (bot API key auth via header)."""
    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    if "num_ai_players" in body:
        return JSONResponse(
            {"error": "num_ai_players is no longer supported; rooms always start with 4 bot seats"},
            status_code=400,
        )

    room_manager = request.app.state.room_manager
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id)

    auth_service = request.app.state.auth_service
    session = auth_service.create_session(
        request.user.user_id,
        request.user.username,
        account_type=request.user.account_type,
    )

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse(
        {"room_id": room_id, "session_id": session.session_id, "ws_url": ws_url},
        status_code=201,
    )
