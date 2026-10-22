from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable

ALREADY_IN_ROOM = "already_in_room"
ALREADY_IN_QUEUE = "already_in_queue"
ALREADY_IN_GAME = "already_in_game"


@dataclass(eq=False)
class _Admission:
    handed_to_game: bool = False


@dataclass
class Occupancy:
    """
    Own the rule that a user is in at most one place: one room, the matchmaking queue, or one game they are playing.

    Rooms and matchmaking each get ``find_lobby_conflict`` from ``create_app()`` and run it in the same synchronous step
    that seats or queues the user, so a seat and a queue place exclude each other atomically on the event loop. Their
    WebSocket handlers await ``find_game_conflict`` before that step, inside ``admitting``: the game servers' answer can
    be stale by the time the lock is taken, since a start may hand the user's seat or queue place to a new game while
    the lookup is in flight. Every attempt to create a game calls ``hand_to_game`` once the game server call is over,
    whatever its outcome (a failure may mean the game exists), and before the seats or the matched players are released;
    ``find_lobby_conflict`` then rejects every admission of those users that was open at that moment.
    """

    is_seated: Callable[[str], bool]
    is_queued: Callable[[str], bool]
    is_playing: Callable[[str], Awaitable[bool]]
    _admissions: dict[str, set[_Admission]] = field(default_factory=dict, init=False)

    @contextlib.contextmanager
    def admitting(self, user_id: str) -> Generator[None]:
        """
        Track one attempt to seat or queue the user, from before its game lookup until its locked step has run.
        """
        admission = _Admission()
        self._admissions.setdefault(user_id, set()).add(admission)
        try:
            yield
        finally:
            admissions = self._admissions[user_id]
            admissions.discard(admission)
            if not admissions:
                del self._admissions[user_id]

    def hand_to_game(self, user_ids: Iterable[str]) -> None:
        """
        Record that an attempt to create a game for these users ended, invalidating the lookups of their open
        admissions.
        """
        for user_id in user_ids:
            for admission in self._admissions.get(user_id, ()):
                admission.handed_to_game = True

    def find_lobby_conflict(self, user_id: str) -> str | None:
        """
        Return why the user cannot take a room seat or a queue place, or None.

        The user is already in a game when a start handed them to one during an open admission, already in a room when
        seated in any room, and already in the queue when queued or matched.
        """
        if any(admission.handed_to_game for admission in self._admissions.get(user_id, ())):
            return ALREADY_IN_GAME

        if self.is_seated(user_id):
            return ALREADY_IN_ROOM

        if self.is_queued(user_id):
            return ALREADY_IN_QUEUE

        return None

    async def find_game_conflict(self, user_id: str) -> str | None:
        """
        Return ``already_in_game`` when the user is playing a game, or None.
        """
        if await self.is_playing(user_id):
            return ALREADY_IN_GAME

        return None
