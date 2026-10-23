from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from lobby.matchmaking.models import MATCHMAKING_SEATS

if TYPE_CHECKING:
    from collections.abc import Callable

    from lobby.players import LobbyPlayer

logger = structlog.get_logger()


def _no_conflict(_user_id: str) -> str | None:
    return None


class MatchmakingManager:
    """
    Manage the matchmaking queue.

    Pure state management -- no WebSocket I/O. The WebSocket handler calls manager methods and handles responses. Every
    method is synchronous, so each runs atomically on the event loop and the queue needs no lock.
    `find_conflict` is the occupancy rule ``create_app()`` injects (``lobby.occupancy``), the only link to the rooms
    feature: it returns why a user cannot queue, or None.
    """

    def __init__(self, *, find_conflict: Callable[[str], str | None] = _no_conflict) -> None:
        self._find_conflict = find_conflict
        self._queue: list[LobbyPlayer] = []
        self._user_ids: set[str] = set()
        self._in_flight: set[str] = set()

    def add_player(self, player: LobbyPlayer) -> None:
        """
        Add a player to the matchmaking queue.

        Raise ValueError with the occupancy conflict when the user cannot queue.
        """
        conflict = self._find_conflict(player.user_id)
        if conflict is not None:
            raise ValueError(conflict)

        self._queue.append(player)
        self._user_ids.add(player.user_id)

    def has_user(self, user_id: str) -> bool:
        """
        Check if a user is queued, or matched and waiting for their game to be created.
        """
        return user_id in self._user_ids or user_id in self._in_flight

    def remove_player(self, connection_id: str) -> None:
        """
        Remove a player from the queue by connection_id.
        """
        for i, player in enumerate(self._queue):
            if player.connection_id == connection_id:
                self._user_ids.discard(player.user_id)
                self._queue.pop(i)
                return

    def try_match(self) -> list[LobbyPlayer] | None:
        """
        Pop MATCHMAKING_SEATS players if enough in queue, else None.
        """
        if len(self._queue) >= MATCHMAKING_SEATS:
            matched = self._queue[:MATCHMAKING_SEATS]
            self._queue = self._queue[MATCHMAKING_SEATS:]
            for player in matched:
                self._user_ids.discard(player.user_id)
                self._in_flight.add(player.user_id)

            return matched

        return None

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def get_queued_players(self) -> list[LobbyPlayer]:
        """
        Return a snapshot of the queued players.
        """
        return list(self._queue)

    def clear_in_flight(self, user_ids: set[str]) -> None:
        """
        Remove user IDs from the in-flight set.

        Called once a match is resolved, whether its game was created or not, so every matched user may queue again.
        """
        self._in_flight -= user_ids
