from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from shared.dal.models import GamesSummary, PlayedGame


class GameRepository(ABC):
    """
    Abstract interface for played game persistence.

    The two writes are posted: they return at once, run in call order, and a failure is logged, never raised, so a
    game never waits on its own record.
    """

    @abstractmethod
    def create_game(self, game: PlayedGame) -> None:
        """
        Record a game's start; a game already recorded keeps its row.
        """

    @abstractmethod
    def finish_game(self, game: PlayedGame) -> None:
        """
        Record a finished game whole, with or without its start row; a game already finished keeps its first finish.
        """

    @abstractmethod
    async def get_recent_completed_games(self, limit: int = 20) -> list[PlayedGame]:
        """
        Return the most recently started completed games, newest first.
        """

    @abstractmethod
    async def get_games_summary(self, *, since: datetime) -> GamesSummary:
        """
        Summarize the games started at or after ``since``, a UTC-aware datetime.
        """
