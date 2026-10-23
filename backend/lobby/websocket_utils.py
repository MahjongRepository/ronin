from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.settings import LobbyServerSettings


def check_origin(websocket: WebSocket) -> bool:
    """
    Verify the WebSocket origin header against the allowed origin setting.
    """
    settings: LobbyServerSettings = websocket.app.state.settings
    return websocket.headers.get("origin") == settings.ws_allowed_origin
