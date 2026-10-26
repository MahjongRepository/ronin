from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from lobby.players import LobbyPlayer
from shared.websocket import QueuedWebSocket, accept_websocket, reject_websocket

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.websockets import WebSocket

    from lobby.settings import LobbyServerSettings


def _check_origin(websocket: WebSocket) -> bool:
    """
    Verify the WebSocket origin header against the allowed origin setting.
    """
    settings: LobbyServerSettings = websocket.app.state.settings
    return websocket.headers.get("origin") == settings.ws_allowed_origin


async def serve_lobby_socket(websocket: WebSocket, serve: Callable[[LobbyPlayer], Awaitable[None]]) -> None:
    """
    Admit a room or matchmaking socket and hand its player to ``serve``; this task owns the connection's writer.

    A socket with a foreign ``Origin`` is refused with 4003 and an unauthenticated one with 4001, both before accept.
    The writer runs while ``serve`` does and is stopped however it ends; ``serve`` decides what an unexpected error
    does.
    """
    if not _check_origin(websocket):
        await reject_websocket(websocket, code=4003, reason="forbidden_origin")
        return

    if not websocket.user.is_authenticated:
        await reject_websocket(websocket, code=4001, reason="unauthorized")
        return

    if not await accept_websocket(websocket):
        return

    connection_id = str(uuid.uuid4())
    player = LobbyPlayer(
        connection_id=connection_id,
        user_id=websocket.user.user_id,
        username=websocket.user.username,
        connection=QueuedWebSocket(websocket, connection_id=connection_id),
    )
    player.connection.start_writer()
    try:
        await serve(player)
    finally:
        await player.connection.stop_writer()
