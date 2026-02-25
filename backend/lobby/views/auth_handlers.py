"""Auth endpoints: login, register, logout, bot auth, and bot room creation for the lobby."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse, RedirectResponse, Response

from shared.auth.service import AuthError
from shared.auth.session_store import DEFAULT_SESSION_TTL_SECONDS

MAX_AI_PLAYERS = 3

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
    """GET /login - render login form."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html", {"error": None})


async def login(request: Request) -> Response:
    """POST /login - validate credentials, set session cookie, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    templates = request.app.state.templates
    form = await request.form()

    username = form.get("username", "")
    password = form.get("password", "")

    try:
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": str(e)},
        )

    return _redirect_with_session_cookie(session, auth_settings)


async def register_page(request: Request) -> Response:
    """GET /register - render registration form."""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "register.html", {"error": None})


async def register(request: Request) -> Response:
    """POST /register - create account, auto-login, redirect to lobby."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    templates = request.app.state.templates
    form = await request.form()

    username = form.get("username", "")
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")

    if password != confirm_password:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Passwords do not match"},
        )

    try:
        await auth_service.register(str(username), str(password))
        session = await auth_service.login(str(username), str(password))
    except AuthError as e:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": str(e)},
        )
    return _redirect_with_session_cookie(session, auth_settings)


async def logout(request: Request) -> Response:
    """POST /logout - clear session, redirect to login."""
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
    session = auth_service.create_session(request.user.user_id, request.user.username)

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse({"session_id": session.session_id, "room_id": room_id, "ws_url": ws_url})


async def bot_create_room(request: Request) -> Response:
    """POST /api/rooms {num_ai_players?} - create a room (bot API key auth via header)."""
    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    num_ai_players = body.get("num_ai_players", MAX_AI_PLAYERS)
    if not isinstance(num_ai_players, int) or not 0 <= num_ai_players <= MAX_AI_PLAYERS:
        return JSONResponse({"error": "num_ai_players must be an integer 0-3"}, status_code=400)

    room_manager = request.app.state.room_manager
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id, num_ai_players=num_ai_players)

    auth_service = request.app.state.auth_service
    session = auth_service.create_session(request.user.user_id, request.user.username)

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse(
        {"room_id": room_id, "session_id": session.session_id, "ws_url": ws_url},
        status_code=201,
    )
