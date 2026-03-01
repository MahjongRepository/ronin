"""Shared WebSocket utilities for lobby handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.server.settings import LobbyServerSettings


def check_origin(websocket: WebSocket) -> bool:
    """Verify the WebSocket origin header against the allowed origin setting."""
    settings: LobbyServerSettings = websocket.app.state.settings
    ws_allowed_origin = settings.ws_allowed_origin
    if not ws_allowed_origin:
        return True
    origin = websocket.headers.get("origin", "")
    return origin == ws_allowed_origin
