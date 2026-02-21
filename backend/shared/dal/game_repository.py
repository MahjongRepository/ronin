"""Abstract interface for played game persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from shared.dal.models import PlayedGame


class GameRepository(ABC):
    """Abstract interface for played game persistence."""

    @abstractmethod
    async def create_game(self, game: PlayedGame) -> None: ...

    @abstractmethod
    async def finish_game(
        self,
        game_id: str,
        ended_at: datetime,
        end_reason: str = "completed",
    ) -> None: ...

    @abstractmethod
    async def get_game(self, game_id: str) -> PlayedGame | None: ...

    @abstractmethod
    async def get_games_by_player(self, player_id: str) -> list[PlayedGame]: ...  # deadcode: ignore
