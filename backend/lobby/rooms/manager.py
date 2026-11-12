from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from lobby.rooms.models import LobbyRoom
from lobby.rooms.names import pick_room_name
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Callable

    from lobby.players import LobbyPlayer
    from lobby.rooms.models import RoomMember

logger = structlog.get_logger()


def _no_conflict(_user_id: str, _room_id: str) -> str | None:
    return None


def _announce_nothing(_room: LobbyRoom, *, player: LobbyPlayer, was_host: bool) -> None:
    pass


def _announce_no_expiry(_room: LobbyRoom) -> None:
    pass


@dataclass(frozen=True)
class RoomJoin:
    """
    A join that seated its player: ``displaced`` is the connection whose seat it took over, or None for a new seat.
    """

    room: LobbyRoom
    displaced: LobbyPlayer | None = None


class LobbyRoomManager:
    """
    Manages pre-game rooms on the lobby server.

    State management: the WebSocket handler calls the manager and sends the responses. ``create_app()`` injects the
    links to the rest of the lobby. ``find_conflict`` is the occupancy rule (``lobby.occupancy``), the only link to
    the matchmaking feature: given a user and a room, it returns why the user cannot be seated there (seated in another
    room, or queued), or None, which also admits a user already seated in that room to take their seat over.
    ``announce_departure`` is the rooms handler's announcement of a released seat, which the reaper makes when a held
    seat's grace runs out, and ``announce_expiry`` its notice to the players of a room the reaper closed.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        unclaimed_room_ttl_seconds: float = 300,
        room_ttl_seconds: float = 3600,
        seat_grace_seconds: float = 300,
        reaper_interval_seconds: float = 30,
        find_conflict: Callable[[str, str], str | None] = _no_conflict,
        announce_departure: Callable[..., None] = _announce_nothing,
        announce_expiry: Callable[[LobbyRoom], None] = _announce_no_expiry,
    ) -> None:
        self._find_conflict = find_conflict
        self._announce_departure = announce_departure
        self._announce_expiry = announce_expiry
        self._rooms: dict[str, LobbyRoom] = {}
        self._unclaimed_room_ttl_seconds = unclaimed_room_ttl_seconds
        self._room_ttl_seconds = room_ttl_seconds
        self._seat_grace_seconds = seat_grace_seconds
        self._reaper_interval_seconds = reaper_interval_seconds
        self._reaper_task: asyncio.Task[None] | None = None

    def create_room(self, room_id: str, *, min_human_players: int = 1) -> LobbyRoom:
        """
        Create a new room with 4 bot seats, named apart from every open room.
        """
        name = pick_room_name({room.name for room in self._rooms.values()})
        room = LobbyRoom(room_id=room_id, name=name, min_human_players=min_human_players)
        self._rooms[room_id] = room
        logger.info("room created", room_id=room_id, room_name=name, min_human_players=min_human_players)
        return room

    def join_room(self, *, room_id: str, player: LobbyPlayer) -> RoomJoin | str:
        """
        Seat the player in the first bot seat of the room, or hand them the seat their user already holds there; return
        the join, or the error string.

        The occupancy rule runs first, so a join that a start handed to its game while the join's playing lookup was in
        flight is refused as ``already_in_game`` (and handed that game) even though the start has since removed or
        reopened the room. A takeover swaps only the member's connection, so the seat, the ready flag and the arrival
        (and with it the ownership order) stay, and it needs no open seat; it ends a hold on the seat. A transitioning
        room refuses every other join, takeovers included: the start has already listed its players, and their tickets
        go to the connections it listed.
        """
        conflict = self._find_conflict(player.user_id, room_id)
        if conflict is not None:
            return conflict

        room = self._rooms.get(room_id)
        if room is None:
            return "room_not_found"

        if room.transitioning:
            return "room_transitioning"

        member = room.member_of_user(player.user_id)
        if member is not None:
            displaced, member.player = member.player, player
            member.disconnected_at = None
            return RoomJoin(room=room, displaced=displaced)

        seat = room.first_open_seat()
        if seat is None:
            return "room_full"

        room.seat_player(seat, player)
        return RoomJoin(room=room)

    def leave_room(self, room_id: str, connection_id: str) -> bool:
        """
        Remove a player from the room, restoring their seat to a bot; return False when they were not seated there.

        While the room is transitioning the seat is held instead (the player's ticket is already signed, and the game
        server replaces a human who never connects with AI): no host transfer, and the room stays even when every player
        has left. The transition settles it: ``clear_transitioning`` on failure, ``remove_room`` on success.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return False

        member = room.member(connection_id)
        if member is None:
            return False

        if room.transitioning:
            member.departed = True
            return True

        room.vacate_seat(member)
        if room.is_empty:
            self._rooms.pop(room_id, None)

        return True

    def hold_seat(self, room_id: str, connection_id: str) -> bool:
        """
        Keep the seat of a player whose connection was lost for ``seat_grace_seconds``; return False when there is none.

        The held member stays seated as it was (ready flag, ownership), so the room waits for its reconnect, which takes
        the seat over, and the reaper releases it once the grace runs out. A transitioning room holds nothing: its leave
        rule already keeps the seat for the game.
        """
        room = self._rooms.get(room_id)
        if room is None or room.transitioning:
            return False

        member = room.member(connection_id)
        if member is None:
            return False

        member.disconnected_at = time.monotonic()
        return True

    def is_seat_held(self, user_id: str) -> bool:
        """
        Check if the user's seat is held for a lost connection, which a join elsewhere may release.
        """
        return self._find_held_seat(user_id) is not None

    def release_held_seat(self, user_id: str) -> None:
        """
        Release the user's seat when it is held for a lost connection, announcing it like a leave.

        A handler calls it right after seating or queueing the user elsewhere: a page that lost its socket could not
        tell the server it left.
        """
        held = self._find_held_seat(user_id)
        if held is not None:
            self._release_seat(*held)

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

        member = room.member(connection_id)
        if member is None:
            return "not_in_room"

        if member is room.host:
            return "owner_cannot_ready"

        member.ready = ready
        return room

    def start_game(self, room_id: str, connection_id: str) -> str | None:
        """
        Mark the room as transitioning when its owner may start it; return the error string, or None on success.

        The caller reads ``num_ai_players`` from the room.
        """
        room = self._rooms.get(room_id)
        if room is None or room.member(connection_id) is None:
            return "not_in_room"

        if room.transitioning:
            return "room_transitioning"

        if not room.is_host(connection_id):
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
        for member in room.members:
            if member.departed:
                room.vacate_seat(member)
            else:
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
                "name": room.name,
                "player_count": room.player_count,
                "num_ai_players": room.num_ai_players,
                "players": [p.model_dump() for p in room.get_player_info()],
            }
            for room in self._rooms.values()
            if not room.transitioning
        ]

    def find_user_room(self, user_id: str) -> str | None:
        """
        Return the id of the room the user is seated in, or None.
        """
        return next((room.room_id for room in self._rooms.values() if room.member_of_user(user_id) is not None), None)

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
        Periodically reap rooms and held seats; a failed tick is logged and the next one still runs.
        """
        while True:
            await asyncio.sleep(self._reaper_interval_seconds)
            try:
                self._reap()
            except Exception:
                logger.exception("room reaper tick failed")

    def _reap(self) -> None:
        """
        Remove expired rooms, and release the held seats whose grace ran out.

        A room nobody joined expires ``unclaimed_room_ttl_seconds`` after creation, a joined one ``room_ttl_seconds``
        after it, its players told and their sockets closed; a transitioning room never expires. One synchronous pass:
        an announcement is an enqueue on each connection, so no room waits on another room's slow socket, and no join or
        start can interleave with the tick.
        """
        now = time.monotonic()
        for room in list(self._rooms.values()):
            age = now - room.created_at
            if room.is_empty:
                if age > self._unclaimed_room_ttl_seconds:
                    self.remove_room(room.room_id)
                    logger.info("unclaimed room expired", room_id=room.room_id)
            elif room.transitioning:
                continue
            elif age > self._room_ttl_seconds:
                self.remove_room(room.room_id)
                logger.info("room expired", room_id=room.room_id)
                self._announce_expiry(room)
            else:
                for member in room.members:
                    if self._is_hold_expired(member, now):
                        self._release_seat(room, member)

    def _find_held_seat(self, user_id: str) -> tuple[LobbyRoom, RoomMember] | None:
        for room in self._rooms.values():
            member = room.member_of_user(user_id)
            if member is not None and member.disconnected_at is not None and not room.transitioning:
                return room, member

        return None

    def _is_hold_expired(self, member: RoomMember, now: float) -> bool:
        return member.disconnected_at is not None and now - member.disconnected_at > self._seat_grace_seconds

    def _release_seat(self, room: LobbyRoom, member: RoomMember) -> None:
        was_host = room.host is member
        self.leave_room(room.room_id, member.player.connection_id)
        logger.info("held room seat released", room_id=room.room_id, username=member.player.username)
        self._announce_departure(room, player=member.player, was_host=was_host)
