from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from lobby.rooms.models import LobbyPlayer, LobbyRoom
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()


def _no_conflict(_user_id: str) -> str | None:
    return None


class LobbyRoomManager:
    """
    Manages pre-game rooms on the lobby server.

    Purely state management — no WebSocket I/O. The WebSocket handler calls manager methods and sends responses.
    ``find_conflict`` is the occupancy rule ``create_app()`` injects (``lobby.occupancy``), the only link to the
    matchmaking feature: it returns why a user cannot take a seat (seated in any room, this one included, or queued), or
    None.
    """

    def __init__(
        self,
        room_ttl_seconds: int = 300,
        reaper_interval_seconds: float = 30,
        on_room_expired: Callable[[str, list[str]], Awaitable[None]] | None = None,
        find_conflict: Callable[[str], str | None] = _no_conflict,
    ) -> None:
        self._find_conflict = find_conflict
        self._rooms: dict[str, LobbyRoom] = {}
        self._player_rooms: dict[str, str] = {}  # connection_id -> room_id
        self._room_ttl_seconds = room_ttl_seconds
        self._reaper_interval_seconds = reaper_interval_seconds
        self._on_room_expired = on_room_expired
        self._reaper_task: asyncio.Task[None] | None = None

    def create_room(self, room_id: str, *, min_human_players: int = 1) -> LobbyRoom:
        """
        Create a new room with 4 bot seats.
        """
        room = LobbyRoom(room_id=room_id, min_human_players=min_human_players)
        self._rooms[room_id] = room
        logger.info("room created", room_id=room_id, min_human_players=min_human_players)
        return room

    def join_room(
        self,
        *,
        connection_id: str,
        room_id: str,
        user_id: str,
        username: str,
    ) -> dict | str:
        """
        Join a room, taking the first available bot seat.

        Returns room state dict on success, or error string on failure.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return "room_not_found"

        if room.transitioning:
            return "room_transitioning"

        if room.is_full:
            return "room_full"

        conflict = self._find_conflict(user_id)
        if conflict is not None:
            return conflict

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
        """
        Remove a player from their room, restoring their seat to a bot.

        While the room is transitioning the seat is held instead (the player's ticket is already signed, and the game
        server replaces a human who never connects with AI): no host transfer, and the room stays even when every player
        has left. The transition settles it: ``clear_transitioning`` on failure, ``remove_room`` on success.
        """
        room_id = self._player_rooms.pop(connection_id, None)
        if room_id is None:
            return None

        room = self._rooms.get(room_id)
        if room is None:
            return room_id

        if room.transitioning:
            room.players[connection_id].departed = True
            return room_id

        self._release_seat(room, connection_id)
        if room.is_empty:
            self._rooms.pop(room_id, None)

        return room_id

    @staticmethod
    def _release_seat(room: LobbyRoom, connection_id: str) -> None:
        seat = room.seat_of(connection_id)
        if seat is not None:
            room.seats[seat] = None

        room.players.pop(connection_id, None)

        if room.host_connection_id == connection_id:
            room.host_connection_id = next(iter(room.players), None)

    def set_ready(self, connection_id: str, *, ready: bool) -> tuple[str, bool] | str:
        """
        Set ready state.

        Returns (room_id, can_start) or error string. Owner cannot set ready — they use start_game instead.
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
        """
        Undo a game start that failed before the game was created.

        Reset the transitioning flag and every ready state, release the seats of players who left during the transition,
        and drop the room if none is left. The rooms handler never empties a room this way (its host runs the transition
        and cannot leave during it); the drop is kept for C20's shared ``start_game``.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return

        room.transitioning = False
        departed = [conn_id for conn_id, player in room.players.items() if player.departed]
        for conn_id in departed:
            self._release_seat(room, conn_id)

        for player in room.players.values():
            player.ready = False

        if room.is_empty:
            self._rooms.pop(room_id, None)

    def get_room(self, room_id: str) -> LobbyRoom | None:
        return self._rooms.get(room_id)

    def get_rooms_info(self) -> list[dict]:
        """
        Return room info for the lobby listing page.
        """
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

    def has_user_in_any_room(self, user_id: str) -> bool:
        """
        Check if a user is in any active room.
        """
        return any(room.has_user(user_id) for room in self._rooms.values())

    def remove_room(self, room_id: str) -> None:
        """
        Remove a room after game starts successfully.
        """
        room = self._rooms.pop(room_id, None)
        if room is not None:
            for conn_id in list(room.players):
                self._player_rooms.pop(conn_id, None)

    def start_reaper(self) -> None:
        """
        Start the periodic room reaper task.
        """
        if self._reaper_task is not None:
            return

        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def stop_reaper(self) -> None:
        """
        Cancel the reaper task.
        """
        if self._reaper_task is not None:
            await cancel_and_wait([self._reaper_task])
            self._reaper_task = None

    async def _reaper_loop(self) -> None:
        """
        Periodically remove expired rooms; a failed tick is logged and the next one still runs.
        """
        while True:
            await asyncio.sleep(self._reaper_interval_seconds)
            try:
                await self._reap_expired_rooms()
            except Exception:
                logger.exception("room reaper tick failed")

    def _is_expired(self, room: LobbyRoom, now: float) -> bool:
        return not room.transitioning and now - room.created_at > self._room_ttl_seconds

    async def _reap_expired_rooms(self) -> None:
        """
        Remove rooms that have exceeded their TTL and disconnect their players.

        Each room is re-checked, removed and closed under its ``join_lock``, so a join in progress finishes (and its
        connection is registered) before the room's connections are closed, and a start that won the lock is kept.
        """
        now = time.monotonic()
        candidates = [(room_id, room) for room_id, room in self._rooms.items() if self._is_expired(room, now)]
        for room_id, room in candidates:
            async with room.join_lock:
                if self._rooms.get(room_id) is not room or not self._is_expired(room, now):
                    continue

                connection_ids = list(room.players.keys())
                self.remove_room(room_id)
                logger.info("room expired", room_id=room_id)
                await self._notify_room_expired(room_id, connection_ids)

    async def _notify_room_expired(self, room_id: str, connection_ids: list[str]) -> None:
        if self._on_room_expired is None:
            return

        try:
            await self._on_room_expired(room_id, connection_ids)
        except Exception:
            logger.exception("error in on_room_expired callback", room_id=room_id)
