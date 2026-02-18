"""Auth endpoints: login, register, logout, and bot auth for the lobby."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse, RedirectResponse, Response

from lobby.games.service import RoomCreationError
from lobby.games.types import MAX_AI_PLAYERS
from lobby.views.handlers import build_websocket_url, create_signed_ticket
from shared.auth.models import AccountType
from shared.auth.service import AuthError, AuthService
from shared.auth.session_store import DEFAULT_SESSION_TTL_SECONDS

if TYPE_CHECKING:
    from starlette.requests import Request

    from shared.auth.models import AuthSession, User
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


async def _validate_bot_api_key(auth_service: AuthService, api_key: str) -> User | None:
    """Validate a bot API key. Return the User if valid, otherwise None."""
    user = await auth_service.validate_api_key(api_key)
    if user is None or user.account_type != AccountType.BOT:
        return None
    return user


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
    """POST /api/auth/bot {api_key, room_id} - exchange API key for game ticket."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    games_service = request.app.state.games_service

    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    api_key = body.get("api_key")
    room_id = body.get("room_id")

    if not isinstance(api_key, str) or not isinstance(room_id, str) or not api_key or not room_id:
        return JSONResponse({"error": "api_key and room_id are required as non-empty strings"}, status_code=400)

    user = await _validate_bot_api_key(auth_service, api_key)
    if user is None:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)

    rooms = await games_service.list_rooms()
    room = next((r for r in rooms if r["room_id"] == room_id), None)
    if room is None:
        return JSONResponse({"error": "Room not found"}, status_code=404)

    ws_url = build_websocket_url(room["server_url"], room_id)
    signed = create_signed_ticket(user.user_id, user.username, room_id, auth_settings.game_ticket_secret)
    return JSONResponse({"game_ticket": signed, "ws_url": ws_url})


async def bot_create_room(request: Request) -> Response:
    """POST /api/rooms/create {api_key, num_ai_players?} - create room and return game ticket."""
    auth_service = request.app.state.auth_service
    auth_settings = request.app.state.auth_settings
    games_service = request.app.state.games_service

    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    api_key = body.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        return JSONResponse({"error": "api_key is required as a non-empty string"}, status_code=400)

    num_ai_players = body.get("num_ai_players", MAX_AI_PLAYERS)
    if (
        isinstance(num_ai_players, bool)
        or not isinstance(num_ai_players, int)
        or num_ai_players < 0
        or num_ai_players > MAX_AI_PLAYERS
    ):
        return JSONResponse(
            {"error": f"num_ai_players must be an integer between 0 and {MAX_AI_PLAYERS}"},
            status_code=400,
        )

    user = await _validate_bot_api_key(auth_service, api_key)
    if user is None:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)

    try:
        result = await games_service.create_room(num_ai_players=num_ai_players)
    except RoomCreationError as e:
        return JSONResponse({"error": str(e)}, status_code=503)

    signed = create_signed_ticket(user.user_id, user.username, result.room_id, auth_settings.game_ticket_secret)
    return JSONResponse(
        {
            "room_id": result.room_id,
            "game_ticket": signed,
            "ws_url": result.websocket_url,
        },
        status_code=201,
    )
