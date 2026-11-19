from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from urllib.parse import quote

import structlog

from lobby.game_transition import GameLookupError, find_game_handoff

if TYPE_CHECKING:
    import httpx
    from starlette.requests import Request

    from lobby.rooms.manager import LobbyRoomManager
    from lobby.settings import LobbyServerSettings

logger = structlog.get_logger()


def open_new_room(room_manager: LobbyRoomManager) -> str:
    """
    Create a local room under a fresh id and return the id.
    """
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id)
    return room_id


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
