from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from lobby.matchmaking.models import MATCHMAKING_SEATS, QueueEntry

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()


def _no_conflict(_user_id: str) -> str | None:
    return None


class MatchmakingManager:
    """
    Manage the matchmaking queue.

    Pure state management -- no WebSocket I/O. The WebSocket handler calls manager methods and handles responses.
    `find_conflict` is the occupancy rule ``create_app()`` injects (``lobby.occupancy``), the only link to the rooms
    feature: it returns why a user cannot queue, or None.
    """

    def __init__(self, *, find_conflict: Callable[[str], str | None] = _no_conflict) -> None:
        self._find_conflict = find_conflict
        self._queue: list[QueueEntry] = []
        self._user_ids: set[str] = set()
        self._in_flight: set[str] = set()
        self._lock = asyncio.Lock()

    def add_player(self, entry: QueueEntry) -> None:
        """
        Add a player to the matchmaking queue.

        Caller must hold self._lock. Raise ValueError with the occupancy conflict when the user cannot queue.
        """
        conflict = self._find_conflict(entry.user_id)
        if conflict is not None:
            raise ValueError(conflict)

        self._queue.append(entry)
        self._user_ids.add(entry.user_id)

    def has_user(self, user_id: str) -> bool:
        """
        Check if a user is queued, or matched and waiting for their game to be created.
        """
        return user_id in self._user_ids or user_id in self._in_flight

    def remove_player(self, connection_id: str) -> None:
        """
        Remove a player from the queue by connection_id.

        Caller must hold self._lock.
        """
        for i, entry in enumerate(self._queue):
            if entry.connection_id == connection_id:
                self._user_ids.discard(entry.user_id)
                self._queue.pop(i)
                return

    def try_match(self) -> list[QueueEntry] | None:
        """
        Pop MATCHMAKING_SEATS players if enough in queue, else None.

        Caller must hold self._lock.
        """
        if len(self._queue) >= MATCHMAKING_SEATS:
            matched = self._queue[:MATCHMAKING_SEATS]
            self._queue = self._queue[MATCHMAKING_SEATS:]
            for entry in matched:
                self._user_ids.discard(entry.user_id)
                self._in_flight.add(entry.user_id)

            return matched

        return None

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def get_queue_entries(self) -> list[QueueEntry]:
        """
        Return a snapshot of current queue entries.

        Caller must hold self._lock.
        """
        return list(self._queue)

    def clear_in_flight(self, user_ids: set[str]) -> None:
        """
        Remove user IDs from the in-flight set.

        Called once a match is resolved, whether its game was created or not, so every matched user may queue again.
        Caller must hold self._lock.
        """
        self._in_flight -= user_ids
