from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from app.players import LobbyPlayer


class BotPool:
    """
    Hold the bot accounts standing by for a room's open seats: the idle ones, and the claimed ones in flight.

    Pure state management, like ``MatchmakingManager``: every method is synchronous, so each runs atomically on the
    event loop. ``find_conflict`` is the occupancy rule ``create_app()`` injects (``Occupancy.find_standby_conflict``).
    A claimed bot leaves idle for good; its id stays in flight until ``clear_in_flight``, once its game start settled.
    """

    def __init__(self, *, find_conflict: Callable[[str], str | None]) -> None:
        self._find_conflict = find_conflict
        self._idle: list[LobbyPlayer] = []
        self._in_flight: set[str] = set()

    def add(self, player: LobbyPlayer) -> LobbyPlayer | None:
        """
        Put the bot on standby; return the user's older idle connection it took the entry over from, or None.

        Raise ValueError with the occupancy conflict when the user cannot stand by.
        """
        conflict = self._find_conflict(player.user_id)
        if conflict is not None:
            raise ValueError(conflict)

        for i, idle in enumerate(self._idle):
            if idle.user_id == player.user_id:
                self._idle[i] = player
                return idle

        self._idle.append(player)
        return None

    def remove(self, connection_id: str) -> bool:
        """
        Remove the idle entry this connection holds; return False when it holds none (claimed or taken over).
        """
        for i, idle in enumerate(self._idle):
            if idle.connection_id == connection_id:
                del self._idle[i]
                return True

        return False

    def claim(self, count: int) -> list[LobbyPlayer]:
        """
        Take up to ``count`` idle bots at random and hold them in flight.
        """
        claimed = secrets.SystemRandom().sample(self._idle, min(count, len(self._idle)))
        claimed_ids = {player.user_id for player in claimed}
        self._idle = [player for player in self._idle if player.user_id not in claimed_ids]
        self._in_flight |= claimed_ids
        return claimed

    def clear_in_flight(self, user_ids: Iterable[str]) -> None:
        """
        Release claimed bots once their game start settled, whether the game was created or not.
        """
        self._in_flight.difference_update(user_ids)

    @property
    def has_idle(self) -> bool:
        return bool(self._idle)

    def is_standing_by(self, user_id: str) -> bool:
        """
        Check if a user is an idle standby bot, not yet claimed.
        """
        return any(player.user_id == user_id for player in self._idle)

    def is_claimed(self, user_id: str) -> bool:
        """
        Check if a user was claimed for a game that is being created.
        """
        return user_id in self._in_flight
