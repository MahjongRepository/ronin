from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from urllib.parse import quote

import structlog
from starlette.responses import RedirectResponse

from lobby.auth.csrf import validate_csrf
from lobby.game_transition import GameLookupError, find_game_handoff
from lobby.views.assets import render_page

if TYPE_CHECKING:
    import httpx
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.rooms.manager import LobbyRoomManager
    from lobby.settings import LobbyServerSettings

logger = structlog.get_logger()


def _render_lobby(request: Request, *, error: str | None) -> Response:
    """
    Render the lobby page with the locally managed rooms and an optional error message.
    """
    room_manager: LobbyRoomManager = request.app.state.room_manager
    rooms = room_manager.get_rooms_info()
    return render_page(
        request, template_name="lobby.html", context={"rooms": rooms, "username": request.user.username, "error": error}
    )


async def lobby_page(request: Request) -> Response:
    """GET / - render the lobby page with locally managed rooms."""
    return _render_lobby(request, error=None)


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

    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        return _render_lobby(request, error="Room not found")

    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


async def matchmaking_page(request: Request) -> Response:
    """GET /matchmaking - render matchmaking waiting page."""
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/matchmaking"
    return render_page(
        request, template_name="matchmaking.html", context={"ws_url": ws_url, "username": request.user.username}
    )


async def room_page(request: Request) -> Response:
    """
    GET /rooms/{room_id} - render the room page.

    A room that is gone sends the user to the lobby, or to the game page of the game they play: a room is removed once
    its game starts, and the game page recovers a lost handoff on its own.
    """
    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        return RedirectResponse(await _find_live_game_page(request) or "/", status_code=303)

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return render_page(
        request,
        template_name="room.html",
        context={"room_id": room_id, "ws_url": ws_url, "username": request.user.username},
    )


async def _find_live_game_page(request: Request) -> str | None:
    """
    Return the game page of the game the authenticated user plays, or None when they play none or the lookup failed.
    """
    settings: LobbyServerSettings = request.app.state.settings
    game_server: httpx.AsyncClient = request.app.state.game_server
    try:
        handoff = await find_game_handoff(request.user.user_id, settings=settings, game_server=game_server)
    except GameLookupError as e:
        logger.warning("game handoff lookup failed", username=request.user.username, error=str(e))
        return None

    if handoff is None:
        return None

    return f"{handoff.game_client_url}/{quote(handoff.game_id, safe='')}"
