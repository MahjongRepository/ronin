from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from lobby.matchmaking.models import MATCHMAKING_SEATS

if TYPE_CHECKING:
    from collections.abc import Callable

    from lobby.players import LobbyPlayer

logger = structlog.get_logger()


def _no_conflict(_user_id: str) -> str | None:
    return None


@dataclass(frozen=True)
class QueuePlace:
    """
    A queue entry a join holds: its 1-based ``position``, and the connection whose entry it took over, or None.
    """

    position: int
    displaced: LobbyPlayer | None = None


class MatchmakingManager:
    """
    Manage the matchmaking queue.

    Pure state management -- no WebSocket I/O. The WebSocket handler calls manager methods and handles responses. Every
    method is synchronous, so each runs atomically on the event loop and the queue needs no lock.
    `find_conflict` is the occupancy rule ``create_app()`` injects (``lobby.occupancy``), the only link to the rooms
    feature: it returns why a user cannot queue, or None, which also admits a queued user to take their entry over.
    """

    def __init__(self, *, find_conflict: Callable[[str], str | None] = _no_conflict) -> None:
        self._find_conflict = find_conflict
        self._queue: list[LobbyPlayer] = []
        self._in_flight: set[str] = set()

    def add_player(self, player: LobbyPlayer) -> QueuePlace | list[LobbyPlayer]:
        """
        Queue the player; return their queue place, or the matched players when this join completed a match.

        The queue never holds a full table: the join that fills it matches the whole queue, whose players stay held as
        in flight until ``clear_in_flight``, since they leave the queue before their game is created. A user already
        queued keeps their entry and its position, now held by this connection; the queue does not grow, so no match is
        tried. Raise ValueError with the occupancy conflict when the user cannot queue.
        """
        conflict = self._find_conflict(player.user_id)
        if conflict is not None:
            raise ValueError(conflict)

        for i, queued in enumerate(self._queue):
            if queued.user_id == player.user_id:
                self._queue[i] = player
                return QueuePlace(position=i + 1, displaced=queued)

        self._queue.append(player)
        if len(self._queue) < MATCHMAKING_SEATS:
            return QueuePlace(position=len(self._queue))

        matched, self._queue = self._queue, []
        self._in_flight.update(matched_player.user_id for matched_player in matched)
        return matched

    def is_queued(self, user_id: str) -> bool:
        """
        Check if a user waits in the queue, not yet matched.
        """
        return any(player.user_id == user_id for player in self._queue)

    def is_matched(self, user_id: str) -> bool:
        """
        Check if a user is matched and waiting for their game to be created.
        """
        return user_id in self._in_flight

    def remove_player(self, connection_id: str) -> bool:
        """
        Remove a player from the queue by connection_id; return False when that connection was not queued.
        """
        for i, player in enumerate(self._queue):
            if player.connection_id == connection_id:
                del self._queue[i]
                return True

        return False

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
