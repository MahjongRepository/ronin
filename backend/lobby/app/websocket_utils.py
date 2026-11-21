from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.auth.backend import API_KEY_SCOPE
from app.players import LobbyPlayer
from app.queued_websocket import QueuedWebSocket, accept_websocket, reject_websocket

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.websockets import WebSocket

    from app.auth.socket_registry import CredentialSockets
    from app.settings import LobbyServerSettings


def _check_origin(websocket: WebSocket) -> bool:
    """
    Verify the WebSocket origin header against the allowed origin setting; a key-authenticated handshake passes.

    The check defends cookie sessions against cross-site sockets, and a key is never sent by a browser on its own.
    """
    if API_KEY_SCOPE in websocket.auth.scopes:
        return True

    settings: LobbyServerSettings = websocket.app.state.settings
    return websocket.headers.get("origin") == settings.ws_allowed_origin


async def serve_lobby_socket(websocket: WebSocket, serve: Callable[[LobbyPlayer], Awaitable[None]]) -> None:
    """
    Admit a lobby socket and hand its player to ``serve``; this task owns the connection's writer.

    An unauthenticated socket is refused with 4001 and then a cookie-authenticated one with a foreign ``Origin`` with
    4003, both before accept; a key-authenticated socket skips the ``Origin`` check. From before the accept until its
    writer stops the socket is held under its credential, so a revocation at any point cuts it off, and a socket revoked
    during its accept is closed without being served. The writer runs while ``serve`` does and is stopped however it
    ends; ``serve`` decides what an unexpected error does.
    """
    if not websocket.user.is_authenticated:
        await reject_websocket(websocket, code=4001, reason="unauthorized")
        return

    if not _check_origin(websocket):
        await reject_websocket(websocket, code=4003, reason="forbidden_origin")
        return

    connection_id = str(uuid.uuid4())
    connection = QueuedWebSocket(websocket, connection_id=connection_id)
    credential_sockets: CredentialSockets = websocket.app.state.credential_sockets
    with credential_sockets.admitted(websocket.user.credential_hash, connection):
        if not await accept_websocket(websocket):
            return

        player = LobbyPlayer(
            connection_id=connection_id,
            user_id=websocket.user.user_id,
            username=websocket.user.username,
            connection=connection,
        )
        connection.start_writer()
        try:
            if not connection.is_revoked:
                await serve(player)
        finally:
            await connection.stop_writer()
