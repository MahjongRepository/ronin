from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.websocket import QueuedWebSocket


@dataclass(frozen=True, eq=False)
class LobbyPlayer:
    """
    A user connected to a lobby socket, in a room or the matchmaking queue.

    ``connection`` is written by its own writer task, which the socket's handler owns: a send or close is an enqueue
    that never waits on the peer, so no handler is held up by another player's slow or dead socket.
    """

    connection_id: str
    user_id: str
    username: str
    connection: QueuedWebSocket

    def send(self, message: dict) -> None:
        self.connection.send_text(json.dumps(message))
