"""Room manager for the lobby server."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING

import structlog

from lobby.rooms.models import LobbyPlayer, LobbyRoom

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()


class LobbyRoomManager:
    """Manages pre-game rooms on the lobby server.

    Purely state management — no WebSocket I/O. The WebSocket handler calls
    manager methods and sends responses.
    """

    def __init__(
        self,
        room_ttl_seconds: int = 300,
        on_room_expired: Callable[[str, list[str]], Awaitable[None]] | None = None,
    ) -> None:
        self._rooms: dict[str, LobbyRoom] = {}
        self._player_rooms: dict[str, str] = {}  # connection_id -> room_id
        self._room_ttl_seconds = room_ttl_seconds
        self._on_room_expired = on_room_expired
        self._reaper_task: asyncio.Task[None] | None = None

    def create_room(self, room_id: str) -> LobbyRoom:
        """Create a new room with 4 bot seats."""
        room = LobbyRoom(room_id=room_id)
        self._rooms[room_id] = room
        logger.info("room created", room_id=room_id)
        return room

    def join_room(
        self,
        connection_id: str,
        room_id: str,
        user_id: str,
        username: str,
    ) -> dict | str:
        """Join a room, taking the first available bot seat.

        Returns room state dict on success, or error string on failure.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return "room_not_found"
        if room.transitioning:
            return "room_transitioning"
        if room.is_full:
            return "room_full"
        if room.has_user(user_id):
            return "already_in_room"

        seat = room.first_open_seat()
        if seat is None:  # pragma: no cover — guarded by is_full above
            return "room_full"

        player = LobbyPlayer(
            connection_id=connection_id,
            user_id=user_id,
            username=username,
        )
        room.seats[seat] = connection_id
        room.players[connection_id] = player
        self._player_rooms[connection_id] = room_id

        if room.host_connection_id is None:
            room.host_connection_id = connection_id

        return {
            "type": "room_joined",
            "room_id": room_id,
            "player_name": username,
            "is_owner": room.host_connection_id == connection_id,
            "can_start": room.can_start,
            "players": [p.model_dump() for p in room.get_player_info()],
        }

    def leave_room(self, connection_id: str) -> str | None:
        """Remove a player from their room, restoring their seat to a bot."""
        room_id = self._player_rooms.pop(connection_id, None)
        if room_id is None:
            return None
        room = self._rooms.get(room_id)
        if room is None:
            return room_id

        # Clear the specific seat this player occupied
        seat = room.seat_of(connection_id)
        if seat is not None:
            room.seats[seat] = None
        room.players.pop(connection_id, None)

        # Host transfer
        if room.host_connection_id == connection_id:
            if room.players:
                room.host_connection_id = next(iter(room.players))
            else:
                room.host_connection_id = None

        if room.is_empty:
            self._rooms.pop(room_id, None)

        return room_id

    def set_ready(self, connection_id: str, *, ready: bool) -> tuple[str, bool] | str:
        """Set ready state. Returns (room_id, can_start) or error string.

        Owner cannot set ready — they use start_game instead.
        """
        room_id = self._player_rooms.get(connection_id)
        if room_id is None:
            return "not_in_room"
        room = self._rooms.get(room_id)
        if room is None:
            return "not_in_room"
        if room.transitioning:
            return "room_transitioning"

        player = room.players.get(connection_id)
        if player is None:
            return "not_in_room"

        if connection_id == room.host_connection_id:
            return "owner_cannot_ready"

        player.ready = ready
        return (room_id, room.can_start)

    def start_game(self, connection_id: str) -> str | None:
        """Owner starts the game. Returns None on success, or error string.

        On success, sets room.transitioning = True. The caller reads
        room.num_ai_players from the room object.
        """
        room_id = self._player_rooms.get(connection_id)
        if room_id is None:
            return "not_in_room"
        room = self._rooms.get(room_id)
        if room is None:
            return "not_in_room"
        if room.transitioning:
            return "room_transitioning"
        if connection_id != room.host_connection_id:
            return "not_owner"
        if not room.can_start:
            return "not_all_ready"

        room.transitioning = True
        return None

    def clear_transitioning(self, room_id: str) -> None:
        """Reset transitioning flag and all ready states on POST /games failure."""
        room = self._rooms.get(room_id)
        if room is None:
            return
        room.transitioning = False
        for player in room.players.values():
            player.ready = False

    def get_room(self, room_id: str) -> LobbyRoom | None:
        return self._rooms.get(room_id)

    def get_rooms_info(self) -> list[dict]:
        """Return room info for the lobby listing page."""
        return [
            {
                "room_id": room.room_id,
                "player_count": room.player_count,
                "num_ai_players": room.num_ai_players,
                "players": [p.model_dump() for p in room.get_player_info()],
            }
            for room in self._rooms.values()
            if not room.transitioning
        ]

    def remove_room(self, room_id: str) -> None:
        """Remove a room after game starts successfully."""
        room = self._rooms.pop(room_id, None)
        if room is not None:
            for conn_id in list(room.players):
                self._player_rooms.pop(conn_id, None)

    def start_reaper(self) -> None:
        """Start the periodic room reaper task."""
        if self._reaper_task is not None:
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop_reaper(self) -> None:
        """Cancel the reaper task."""
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper_task
            self._reaper_task = None

    async def _reaper_loop(self) -> None:  # pragma: no cover — long-running background loop
        """Periodically remove expired rooms."""
        while True:
            await asyncio.sleep(30)
            await self._reap_expired_rooms()

    async def _reap_expired_rooms(self) -> None:
        """Remove rooms that have exceeded their TTL."""
        now = time.monotonic()
        expired: list[tuple[str, list[str]]] = []

        for room_id, room in list(self._rooms.items()):
            if room.transitioning:
                continue
            if now - room.created_at > self._room_ttl_seconds:
                connection_ids = list(room.players.keys())
                self.remove_room(room_id)
                expired.append((room_id, connection_ids))
                logger.info("room expired", room_id=room_id)

        if self._on_room_expired:
            for room_id, connection_ids in expired:
                try:
                    await self._on_room_expired(room_id, connection_ids)
                except Exception:
                    logger.exception("error in on_room_expired callback", room_id=room_id)
