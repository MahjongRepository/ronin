from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Iterator

    from lobby.players import LobbyPlayer


class LobbyPlayerInfo(BaseModel):
    """
    Player info for room state messages (sent over WebSocket).
    """

    name: str
    ready: bool
    is_bot: bool
    is_owner: bool


@dataclass
class RoomMember:
    """
    A player seated in a room, with the state only a room has.

    ``arrival`` orders the members by when they took their seat, which decides who owns the room: a seat index is not
    join order once a vacated low seat is refilled. ``departed`` marks a player who left while the room was
    transitioning: the seat is held for the game being created until the transition settles.
    """

    player: LobbyPlayer
    arrival: int
    ready: bool = False
    departed: bool = False


TOTAL_SEATS = 4
BOT_NAME_PREFIX = "Tsumogiri Bot"


@dataclass
class LobbyRoom:
    """
    Pre-game room managed by the lobby server.

    ``seats`` is the one record of who is in the room: 4 fixed slots, each a seated member or None (a bot), so leaving
    seat 2 hands that exact seat back to a bot without shifting anyone. The owner is derived, never stored: the earliest
    arrival still seated.
    """

    room_id: str
    transitioning: bool = False
    min_human_players: int = 1
    created_at: float = field(default_factory=time.monotonic)
    seats: list[RoomMember | None] = field(default_factory=lambda: [None] * TOTAL_SEATS)
    _arrivals: Iterator[int] = field(default_factory=itertools.count, init=False, repr=False)

    @property
    def members(self) -> list[RoomMember]:
        """
        Return the seated members in arrival order.
        """
        return sorted((member for member in self.seats if member is not None), key=lambda member: member.arrival)

    @property
    def host(self) -> RoomMember | None:
        """
        Return the room's owner, the earliest arrival still seated, or None when the room is empty.
        """
        members = self.members
        return members[0] if members else None

    @property
    def num_ai_players(self) -> int:
        """Bot count = number of None slots in seats."""
        return self.seats.count(None)

    @property
    def player_count(self) -> int:
        return TOTAL_SEATS - self.num_ai_players

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0

    @property
    def can_start(self) -> bool:
        """
        Owner can start when enough humans have joined and all non-owner humans are ready.

        Requires at least min_human_players humans in the room (default 1). If only the owner is in the room and
        min_human_players is 1 (playing with 3 bots), returns True. Returns False if the room has no players.
        """
        members = self.members
        if not members or len(members) < self.min_human_players:
            return False

        return all(member.ready for member in members[1:])

    def seat_player(self, seat: int, player: LobbyPlayer) -> None:
        """
        Seat the player in the given bot seat as the latest arrival.
        """
        self.seats[seat] = RoomMember(player=player, arrival=next(self._arrivals))

    def vacate_seat(self, member: RoomMember) -> None:
        """
        Hand the member's seat back to a bot.
        """
        for i, seated in enumerate(self.seats):
            if seated is member:
                self.seats[i] = None

    def first_open_seat(self) -> int | None:
        """
        Return the index of the first bot (None) seat, or None if full.
        """
        for i, member in enumerate(self.seats):
            if member is None:
                return i

        return None

    def seat_of(self, connection_id: str) -> int | None:
        """
        Return the seat index for a connection, or None if not seated.
        """
        for i, member in enumerate(self.seats):
            if member is not None and member.player.connection_id == connection_id:
                return i

        return None

    def member(self, connection_id: str) -> RoomMember | None:
        """
        Return the member seated with this connection, or None.
        """
        seat = self.seat_of(connection_id)
        return None if seat is None else self.seats[seat]

    def is_host(self, connection_id: str) -> bool:
        """
        Check if this connection owns the room.
        """
        host = self.host
        return host is not None and host.player.connection_id == connection_id

    def get_player_info(self) -> list[LobbyPlayerInfo]:
        """
        Return info for all 4 seats in fixed seat order.

        Each seat is either a human player or a bot placeholder. Seat positions are stable — they don't shift when
        players join or leave.
        """
        host = self.host
        info: list[LobbyPlayerInfo] = []
        for i, member in enumerate(self.seats):
            if member is None:
                info.append(LobbyPlayerInfo(name=f"{BOT_NAME_PREFIX} {i + 1}", ready=True, is_bot=True, is_owner=False))
            else:
                is_owner = member is host
                info.append(
                    LobbyPlayerInfo(
                        name=member.player.username,
                        ready=is_owner or member.ready,
                        is_bot=False,
                        is_owner=is_owner,
                    ),
                )

        return info

    def has_user(self, user_id: str) -> bool:
        """
        Check if a user is already in this room (prevents multi-tab seat hogging).
        """
        return any(member.player.user_id == user_id for member in self.members)
