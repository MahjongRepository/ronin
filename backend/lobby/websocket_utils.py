from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.settings import LobbyServerSettings

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def check_origin(websocket: WebSocket) -> bool:
    """Verify the WebSocket origin header against the allowed origin setting.

    Loopback variants are treated as equivalent: when the configured origin
    uses a loopback host, the same scheme and port on any loopback host is
    accepted — browsers may use localhost, 127.0.0.1 or [::1] interchangeably
    for the same locally-running page.
    """
    settings: LobbyServerSettings = websocket.app.state.settings
    ws_allowed_origin = settings.ws_allowed_origin
    if not ws_allowed_origin:
        return True

    origin = websocket.headers.get("origin", "")
    return origin == ws_allowed_origin or _loopback_equivalent(origin, ws_allowed_origin)


def _loopback_equivalent(origin: str, allowed: str) -> bool:
    """Return True when both URLs differ only in the loopback host spelling."""
    try:
        parsed_origin = urlparse(origin)
        parsed_allowed = urlparse(allowed)
    except ValueError:
        return False
    return (
        parsed_origin.scheme == parsed_allowed.scheme
        and parsed_origin.port == parsed_allowed.port
        and parsed_origin.hostname in _LOOPBACK_HOSTS
        and parsed_allowed.hostname in _LOOPBACK_HOSTS
    )
