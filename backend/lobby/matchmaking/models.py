from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

MATCHMAKING_SEATS = 4


@dataclass
class QueueEntry:
    """A player waiting in the matchmaking queue."""

    connection_id: str
    user_id: str
    username: str
    websocket: WebSocket
