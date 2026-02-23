"""WebSocket connection manager for lobby rooms."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

logger = structlog.get_logger()


class RoomConnectionManager:
    """Track WebSocket connections per room for message broadcasting."""

    def __init__(self) -> None:
        self._connections: dict[str, dict[str, WebSocket]] = {}  # room_id -> {conn_id -> ws}
        self._connection_rooms: dict[str, str] = {}  # conn_id -> room_id (reverse index)

    def add(self, room_id: str, connection_id: str, websocket: WebSocket) -> None:
        if room_id not in self._connections:
            self._connections[room_id] = {}
        self._connections[room_id][connection_id] = websocket
        self._connection_rooms[connection_id] = room_id

    def remove(self, connection_id: str) -> str | None:
        """Remove a connection and return the room_id it was in, or None."""
        room_id = self._connection_rooms.pop(connection_id, None)
        if room_id is not None and room_id in self._connections:
            self._connections[room_id].pop(connection_id, None)
            if not self._connections[room_id]:
                del self._connections[room_id]
        return room_id

    async def broadcast(self, room_id: str, message: dict, exclude: str | None = None) -> None:
        """Send a JSON message to all connections in a room, optionally excluding one."""
        connections = self._connections.get(room_id, {})
        payload = json.dumps(message)
        for conn_id, ws in list(connections.items()):
            if conn_id == exclude:
                continue
            with contextlib.suppress(ConnectionError, RuntimeError):
                await ws.send_text(payload)

    async def send_to(self, connection_id: str, message: dict) -> bool:
        """Send a JSON message to a specific connection. Returns True on success."""
        room_id = self._connection_rooms.get(connection_id)
        if room_id is None:
            return False
        connections = self._connections.get(room_id, {})
        ws = connections.get(connection_id)
        if ws is None:
            return False
        try:
            await ws.send_text(json.dumps(message))
        except ConnectionError, RuntimeError:
            return False
        return True

    async def close_connections(self, room_id: str, code: int = 1000, reason: str = "") -> None:
        """Close all WebSocket connections in a room."""
        connections = self._connections.pop(room_id, {})
        for conn_id, ws in connections.items():
            self._connection_rooms.pop(conn_id, None)
            with contextlib.suppress(ConnectionError, RuntimeError):
                await ws.close(code=code, reason=reason)
