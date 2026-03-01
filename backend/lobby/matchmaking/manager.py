"""Matchmaking queue manager."""

from __future__ import annotations

import asyncio

import structlog

from lobby.matchmaking.models import MATCHMAKING_SEATS, QueueEntry

logger = structlog.get_logger()


class MatchmakingManager:
    """Manage the matchmaking queue.

    Pure state management -- no WebSocket I/O. The WebSocket handler
    calls manager methods and handles responses.
    """

    def __init__(self) -> None:
        self._queue: list[QueueEntry] = []
        self._user_ids: set[str] = set()
        self._in_flight: set[str] = set()
        self._lock = asyncio.Lock()

    def add_player(self, entry: QueueEntry) -> None:
        """Add a player to the matchmaking queue.

        Caller must hold self._lock.
        """
        if entry.user_id in self._user_ids or entry.user_id in self._in_flight:
            raise ValueError("already_in_queue")
        self._queue.append(entry)
        self._user_ids.add(entry.user_id)

    def remove_player(self, connection_id: str) -> None:
        """Remove a player from the queue by connection_id.

        Caller must hold self._lock.
        """
        for i, entry in enumerate(self._queue):
            if entry.connection_id == connection_id:
                self._user_ids.discard(entry.user_id)
                self._queue.pop(i)
                return

    def try_match(self) -> list[QueueEntry] | None:
        """Pop MATCHMAKING_SEATS players if enough in queue, else None.

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

    def requeue_at_front(self, entries: list[QueueEntry]) -> None:
        """Re-insert entries at the front of the queue.

        Used when game creation fails after popping a match.
        Caller must hold self._lock.
        """
        for entry in reversed(entries):
            self._in_flight.discard(entry.user_id)
            if entry.user_id not in self._user_ids:
                self._queue.insert(0, entry)
                self._user_ids.add(entry.user_id)

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def get_queue_entries(self) -> list[QueueEntry]:
        """Return a snapshot of current queue entries.

        Caller must hold self._lock.
        """
        return list(self._queue)

    def clear_in_flight(self, user_ids: set[str]) -> None:
        """Remove user IDs from the in-flight set.

        Called after match resolution for users not being requeued.
        Caller must hold self._lock.
        """
        self._in_flight -= user_ids

    def has_user(self, user_id: str) -> bool:
        return user_id in self._user_ids or user_id in self._in_flight
