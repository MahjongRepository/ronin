from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from urllib.parse import quote

import structlog
from starlette.responses import RedirectResponse

from lobby.game_transition import GameLookupError, find_game_handoff
from lobby.views.error_pages import validate_csrf

if TYPE_CHECKING:
    import httpx
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.rooms.manager import LobbyRoomManager
    from lobby.settings import LobbyServerSettings

logger = structlog.get_logger()

_TABLE_GONE_REDIRECT = "/?notice=table_gone"


async def create_room_and_redirect(request: Request) -> Response:
    """POST /rooms/new - create a local room and redirect to the room page."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    room_id = open_new_room(request.app.state.room_manager)
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


def open_new_room(room_manager: LobbyRoomManager) -> str:
    """
    Create a local room under a fresh id and return the id.
    """
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id)
    return room_id


async def join_room_and_redirect(request: Request) -> Response:
    """
    POST /rooms/{room_id}/join - redirect to the room page, or to the lobby with a notice when the room is gone.
    """
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        return RedirectResponse(_TABLE_GONE_REDIRECT, status_code=303)

    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


def lobby_websocket_url(request: Request, path: str) -> str:
    """
    Return the lobby WebSocket URL of ``path`` on the origin and scheme the request came in on.
    """
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    return f"{ws_scheme}://{request.url.netloc}{path}"


async def find_live_game_page(request: Request) -> str | None:
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
