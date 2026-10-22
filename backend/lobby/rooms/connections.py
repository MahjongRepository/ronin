from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from lobby.websocket_utils import close_quietly, send_or_drop

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

logger = structlog.get_logger()


class RoomConnectionManager:
    """
    Track WebSocket connections per room for message broadcasting.

    Sends and closes never raise for a dead peer: its frame is dropped and logged, delivery continues to the other
    peers, and the dead peer's own handler cleans up after it.
    """

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, WebSocket]] = {}  # room_id -> {conn_id -> ws}
        self._connection_rooms: dict[str, str] = {}  # conn_id -> room_id (reverse index)

    def add(self, *, room_id: str, connection_id: str, websocket: WebSocket) -> None:
        if room_id not in self._connections:
            self._connections[room_id] = {}

        self._connections[room_id][connection_id] = websocket
        self._connection_rooms[connection_id] = room_id

    def remove(self, connection_id: str) -> str | None:
        """
        Remove a connection and return the room_id it was in, or None.
        """
        room_id = self._connection_rooms.pop(connection_id, None)
        if room_id is not None and room_id in self._connections:
            self._connections[room_id].pop(connection_id, None)
            if not self._connections[room_id]:
                del self._connections[room_id]

        return room_id

    async def broadcast(self, *, room_id: str, message: dict, exclude: str | None = None) -> None:
        """
        Send a JSON message to all connections in a room, optionally excluding one.
        """
        connections = self._connections.get(room_id, {})
        payload = json.dumps(message)
        for conn_id, ws in list(connections.items()):
            if conn_id == exclude:
                continue

            if not await send_or_drop(ws, payload):
                logger.info("dropped message to dead room connection", room_id=room_id, connection_id=conn_id)

    async def send_to(self, connection_id: str, message: dict) -> bool:
        """
        Send a JSON message to a specific connection.

        Returns True on success.
        """
        room_id = self._connection_rooms.get(connection_id)
        if room_id is None:
            return False

        connections = self._connections.get(room_id, {})
        ws = connections.get(connection_id)
        if ws is None:
            return False

        delivered = await send_or_drop(ws, json.dumps(message))
        if not delivered:
            logger.info("dropped message to dead room connection", room_id=room_id, connection_id=connection_id)

        return delivered

    async def close_connections(self, room_id: str, code: int = 1000, reason: str = "") -> None:
        """
        Close all WebSocket connections in a room.

        The room's index entries go before the first close, so none outlives a close that fails.
        """
        connections = self._connections.pop(room_id, {})
        for conn_id in connections:
            self._connection_rooms.pop(conn_id, None)

        for ws in connections.values():
            await close_quietly(ws, code=code, reason=reason)
