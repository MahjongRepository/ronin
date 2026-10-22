from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from starlette.websockets import WebSocketDisconnect

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.settings import LobbyServerSettings


def check_origin(websocket: WebSocket) -> bool:
    """
    Verify the WebSocket origin header against the allowed origin setting.
    """
    settings: LobbyServerSettings = websocket.app.state.settings
    ws_allowed_origin = settings.ws_allowed_origin
    if not ws_allowed_origin:
        return True

    origin = websocket.headers.get("origin", "")
    return origin == ws_allowed_origin


async def send_or_drop(websocket: WebSocket, text: str) -> bool:
    """
    Send a text frame to an accepted socket; return False when the peer is gone.

    After accept, Starlette turns the first failed send into ``WebSocketDisconnect(1006)`` and every later send or close
    on that socket into ``WebSocketDisconnected``, a ``RuntimeError``. Those two are the whole contract: a dead peer's
    failure never reaches the caller.
    """
    try:
        await websocket.send_text(text)
    except WebSocketDisconnect, RuntimeError:
        return False

    return True


async def close_quietly(websocket: WebSocket, *, code: int = 1000, reason: str = "") -> None:
    """
    Close an accepted socket, ignoring a peer that is already gone (same contract as ``send_or_drop``).
    """
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await websocket.close(code=code, reason=reason)
