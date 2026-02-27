"""Lobby and room page handlers."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from starlette.responses import RedirectResponse

from lobby.server.csrf import get_or_create_csrf_token, set_csrf_cookie, validate_csrf

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.templating import Jinja2Templates

    from lobby.rooms.manager import LobbyRoomManager


def _render_lobby_with_error(
    request: Request,
    templates: Jinja2Templates,
    rooms: list[dict],
    username: str,
    error: str,
) -> Response:
    """Render the lobby page with an error message."""
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "username": username,
            "error": error,
            "csrf_token": csrf_token,
        },
    )
    if is_new:  # pragma: no cover — CSRF validation guarantees cookie exists before this path
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def lobby_page(request: Request) -> Response:
    """GET / - render the lobby page with locally managed rooms."""
    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    user = request.user
    rooms = room_manager.get_rooms_info()

    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "username": user.username,
            "error": None,
            "csrf_token": csrf_token,
        },
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def create_room_and_redirect(request: Request) -> Response:
    """POST /rooms/new - create a local room and redirect to the room page."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id)
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


async def join_room_and_redirect(request: Request) -> Response:
    """POST /rooms/{room_id}/join - validate room exists and redirect to room page."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    user = request.user
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        rooms = room_manager.get_rooms_info()
        return _render_lobby_with_error(request, templates, rooms, user.username, "Room not found")

    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


async def room_page(request: Request) -> Response:
    """GET /rooms/{room_id} - render the room page."""
    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        return RedirectResponse("/", status_code=303)

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"

    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "room.html",
        {
            "room_id": room_id,
            "ws_url": ws_url,
            "username": request.user.username,
            "csrf_token": csrf_token,
        },
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response
