from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from lobby.rooms.models import LobbyRoom, RoomMember
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Callable

    from lobby.players import LobbyPlayer

logger = structlog.get_logger()


def _no_conflict(_user_id: str) -> str | None:
    return None


class LobbyRoomManager:
    """
    Manages pre-game rooms on the lobby server.

    State management: the WebSocket handler calls the manager and sends the responses. The only socket work here is the
    reaper's, which enqueues each expired room's 4002 closes. ``find_conflict`` is the occupancy rule ``create_app()``
    injects (``lobby.occupancy``), the only link to the matchmaking feature: it returns why a user cannot take a seat
    (seated in any room, this one included, or queued), or None.
    """

    def __init__(
        self,
        room_ttl_seconds: int = 300,
        reaper_interval_seconds: float = 30,
        find_conflict: Callable[[str], str | None] = _no_conflict,
    ) -> None:
        self._find_conflict = find_conflict
        self._rooms: dict[str, LobbyRoom] = {}
        self._room_ttl_seconds = room_ttl_seconds
        self._reaper_interval_seconds = reaper_interval_seconds
        self._reaper_task: asyncio.Task[None] | None = None

    def create_room(self, room_id: str, *, min_human_players: int = 1) -> LobbyRoom:
        """
        Create a new room with 4 bot seats.
        """
        room = LobbyRoom(room_id=room_id, min_human_players=min_human_players)
        self._rooms[room_id] = room
        logger.info("room created", room_id=room_id, min_human_players=min_human_players)
        return room

    def join_room(self, *, room_id: str, player: LobbyPlayer) -> dict | str:
        """
        Seat the player in the first bot seat of the room.

        Return the ``room_joined`` message on success, or the error string on failure.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return "room_not_found"

        if room.transitioning:
            return "room_transitioning"

        if room.is_full:
            return "room_full"

        conflict = self._find_conflict(player.user_id)
        if conflict is not None:
            return conflict

        seat = room.first_open_seat()
        if seat is None:  # pragma: no cover — guarded by is_full above
            return "room_full"

        room.seats[seat] = player.connection_id
        room.players[player.connection_id] = RoomMember(player=player)

        if room.host_connection_id is None:
            room.host_connection_id = player.connection_id

        return {
            "type": "room_joined",
            "room_id": room_id,
            "player_name": player.username,
            "is_owner": room.host_connection_id == player.connection_id,
            "can_start": room.can_start,
            "players": [p.model_dump() for p in room.get_player_info()],
        }

    def leave_room(self, room_id: str, connection_id: str) -> bool:
        """
        Remove a player from the room, restoring their seat to a bot; return False when they were not seated there.

        While the room is transitioning the seat is held instead (the player's ticket is already signed, and the game
        server replaces a human who never connects with AI): no host transfer, and the room stays even when every player
        has left. The transition settles it: ``clear_transitioning`` on failure, ``remove_room`` on success.
        """
        room = self._rooms.get(room_id)
        if room is None or connection_id not in room.players:
            return False

        if room.transitioning:
            room.players[connection_id].departed = True
            return True

        self._release_seat(room, connection_id)
        if room.is_empty:
            self._rooms.pop(room_id, None)

        return True

    @staticmethod
    def _release_seat(room: LobbyRoom, connection_id: str) -> None:
        seat = room.seat_of(connection_id)
        if seat is not None:
            room.seats[seat] = None

        room.players.pop(connection_id, None)

        if room.host_connection_id == connection_id:
            room.host_connection_id = next(iter(room.players), None)

    def set_ready(self, room_id: str, connection_id: str, *, ready: bool) -> LobbyRoom | str:
        """
        Set a player's ready state; return the room, or the error string.

        The owner cannot set ready: they use start_game instead.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return "not_in_room"

        if room.transitioning:
            return "room_transitioning"

        member = room.players.get(connection_id)
        if member is None:
            return "not_in_room"

        if connection_id == room.host_connection_id:
            return "owner_cannot_ready"

        member.ready = ready
        return room

    def start_game(self, room_id: str, connection_id: str) -> str | None:
        """
        Mark the room as transitioning when its owner may start it; return the error string, or None on success.

        The caller reads ``num_ai_players`` from the room.
        """
        room = self._rooms.get(room_id)
        if room is None or connection_id not in room.players:
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
        and cannot leave during it), so the drop is the manager's own rule.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return

        room.transitioning = False
        departed = [conn_id for conn_id, member in room.players.items() if member.departed]
        for conn_id in departed:
            self._release_seat(room, conn_id)

        for member in room.players.values():
            member.ready = False

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
        self._rooms.pop(room_id, None)

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
                self._reap_expired_rooms()
            except Exception:
                logger.exception("room reaper tick failed")

    def _is_expired(self, room: LobbyRoom, now: float) -> bool:
        return not room.transitioning and now - room.created_at > self._room_ttl_seconds

    def _reap_expired_rooms(self) -> None:
        """
        Remove rooms that have exceeded their TTL and close their players' sockets with 4002.

        One synchronous pass: a close is an enqueue on the player's connection, so no room waits on another room's slow
        socket, and no join or start can interleave with the tick.
        """
        now = time.monotonic()
        expired = [room for room in self._rooms.values() if self._is_expired(room, now)]
        for room in expired:
            self.remove_room(room.room_id)
            logger.info("room expired", room_id=room.room_id)
            for member in room.players.values():
                member.player.connection.close(code=4002, reason="room_expired")
