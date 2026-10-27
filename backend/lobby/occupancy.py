from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable

ALREADY_IN_ROOM = "already_in_room"
ALREADY_IN_QUEUE = "already_in_queue"
ALREADY_IN_GAME = "already_in_game"
MATCH_STARTING = "match_starting"
REPLACED_BY_NEW_CONNECTION = "replaced_by_new_connection"


class RejectionMessage(TypedDict):
    """
    The error a lobby socket is told before it is closed: the reason, and the user's room for ``already_in_room``.
    """

    type: Literal["error"]
    message: str
    room_id: NotRequired[str]


@dataclass(eq=False)
class _Admission:
    handed_to_game: bool = False


@dataclass
class Occupancy:
    """
    Own the rule that a user is in at most one place: one room, the matchmaking queue, or one game they are playing.

    Rooms get ``find_room_conflict`` and matchmaking ``find_queue_conflict`` from ``create_app()``, and each runs it in
    the same synchronous step that seats or queues the user, so a seat and a queue place exclude each other atomically
    on the event loop. Their WebSocket handlers await ``find_game_conflict`` before that step, inside ``admitting``: the
    game server's answer can be stale by the time that step runs, since a start may hand the user's seat or queue place
    to a new game while the lookup is in flight. Every attempt to create a game calls ``hand_to_game`` once the game
    server call is over, whatever its outcome (a failure may mean the game exists), and before the seats or the matched
    players are released; both conflict checks then reject every admission of those users that was open at that moment.

    A user who rejoins the place they already hold (their seat in the same room, or their queue entry before it is
    matched) is admitted: the new connection takes that place over, never a new one. Nothing else moves a user, so a
    seat is never traded for a queue place or another room's seat.
    """

    find_room: Callable[[str], str | None]
    is_queued: Callable[[str], bool]
    is_matched: Callable[[str], bool]
    is_playing: Callable[[str], Awaitable[bool]]
    _admissions: dict[str, set[_Admission]] = field(default_factory=dict, init=False)

    @contextlib.contextmanager
    def admitting(self, user_id: str) -> Generator[None]:
        """
        Track one attempt to seat or queue the user, from before its game lookup until its seating or queueing step has
        run.
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

    def find_room_conflict(self, user_id: str, room_id: str) -> str | None:
        """
        Return why the user cannot be seated in the room, or None: a new seat, or their own seat in it taken over.

        The caller refuses joins to a transitioning room after asking, so a seat whose game is being created is never
        taken over. A matched user gets ``match_starting``, as from the queue: they cannot leave a match, only wait for
        its game.
        """
        if self._was_handed_to_game(user_id):
            return ALREADY_IN_GAME

        seated_room = self.find_room(user_id)
        if seated_room is not None and seated_room != room_id:
            return ALREADY_IN_ROOM

        if self.is_matched(user_id):
            return MATCH_STARTING

        if self.is_queued(user_id):
            return ALREADY_IN_QUEUE

        return None

    def find_queue_conflict(self, user_id: str) -> str | None:
        """
        Return why the user cannot queue, or None: a new queue entry, or their own unmatched entry taken over.

        A matched user waits for their game to be created and is refused as ``match_starting``, a retryable answer: once
        the game exists a new join is handed it as ``already_in_game``, and after a failed start it queues again.
        """
        if self._was_handed_to_game(user_id):
            return ALREADY_IN_GAME

        if self.find_room(user_id) is not None:
            return ALREADY_IN_ROOM

        if self.is_matched(user_id):
            return MATCH_STARTING

        return None

    def _was_handed_to_game(self, user_id: str) -> bool:
        return any(admission.handed_to_game for admission in self._admissions.get(user_id, ()))

    def rejection_message(self, user_id: str, reason: str) -> RejectionMessage:
        """
        Build the error refusing the user's join for ``reason``.

        An ``already_in_room`` refusal names the room the user is seated in, so the page can link to it. The caller
        builds it in the step that found the conflict, so that room is still the user's.
        """
        message: RejectionMessage = {"type": "error", "message": reason}
        room_id = self.find_room(user_id) if reason == ALREADY_IN_ROOM else None
        if room_id is not None:
            message["room_id"] = room_id

        return message

    async def find_game_conflict(self, user_id: str) -> str | None:
        """
        Return ``already_in_game`` when the user is playing a game, or None.
        """
        if await self.is_playing(user_id):
            return ALREADY_IN_GAME

        return None
