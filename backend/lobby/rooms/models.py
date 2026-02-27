"""Room models for the lobby server."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from pydantic import BaseModel


class LobbyPlayerInfo(BaseModel):
    """Player info for room state messages (sent over WebSocket)."""

    name: str
    ready: bool
    is_bot: bool
    is_owner: bool


@dataclass
class LobbyPlayer:
    """Player connected to a lobby room via WebSocket."""

    connection_id: str
    user_id: str
    username: str
    ready: bool = False


TOTAL_SEATS = 4
BOT_NAME_PREFIX = "Tsumogiri Bot"


@dataclass
class LobbyRoom:
    """Pre-game room managed by the lobby server.

    Uses a fixed 4-element seat array where each slot is either a
    connection_id (human) or None (bot). This ensures seat positions
    are stable across join/leave — leaving seat 2 restores that exact
    seat to a bot without shifting other players.
    """

    room_id: str
    host_connection_id: str | None = None
    transitioning: bool = False
    min_human_players: int = 1
    created_at: float = field(default_factory=time.monotonic)
    seats: list[str | None] = field(default_factory=lambda: [None] * TOTAL_SEATS)
    players: dict[str, LobbyPlayer] = field(default_factory=dict)  # connection_id -> LobbyPlayer
    join_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def num_ai_players(self) -> int:
        """Bot count = number of None slots in seats."""
        return self.seats.count(None)

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_full(self) -> bool:
        return None not in self.seats

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0

    @property
    def can_start(self) -> bool:
        """Owner can start when enough humans have joined and all non-owner humans are ready.

        Requires at least min_human_players humans in the room (default 1).
        If only the owner is in the room and min_human_players is 1
        (playing with 3 bots), returns True.
        Returns False if the room has no players.
        """
        if not self.players:
            return False
        if self.player_count < self.min_human_players:
            return False
        return all(p.ready for conn_id, p in self.players.items() if conn_id != self.host_connection_id)

    def first_open_seat(self) -> int | None:
        """Return the index of the first bot (None) seat, or None if full."""
        for i, conn_id in enumerate(self.seats):
            if conn_id is None:
                return i
        return None

    def seat_of(self, connection_id: str) -> int | None:
        """Return the seat index for a connection, or None if not seated."""
        for i, conn_id in enumerate(self.seats):
            if conn_id == connection_id:
                return i
        return None

    def get_player_info(self) -> list[LobbyPlayerInfo]:
        """Return info for all 4 seats in fixed seat order.

        Each seat is either a human player or a bot placeholder.
        Seat positions are stable — they don't shift when players
        join or leave.
        """
        info: list[LobbyPlayerInfo] = []
        for i, conn_id in enumerate(self.seats):
            if conn_id is not None and conn_id in self.players:
                p = self.players[conn_id]
                info.append(
                    LobbyPlayerInfo(
                        name=p.username,
                        ready=True if conn_id == self.host_connection_id else p.ready,
                        is_bot=False,
                        is_owner=conn_id == self.host_connection_id,
                    ),
                )
            else:
                info.append(
                    LobbyPlayerInfo(
                        name=f"{BOT_NAME_PREFIX} {i + 1}",
                        ready=True,
                        is_bot=True,
                        is_owner=False,
                    ),
                )
        return info

    def has_user(self, user_id: str) -> bool:
        """Check if a user is already in this room (prevents multi-tab seat hogging)."""
        return any(p.user_id == user_id for p in self.players.values())
