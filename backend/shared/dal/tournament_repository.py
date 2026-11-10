from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.dal.models import GameEndReason, PlayedGameStanding, Tournament, TournamentGame


class TournamentRepository(ABC):
    """
    Abstract interface for tournament persistence.
    """

    @abstractmethod
    async def create_tournament(self, tournament: Tournament) -> None: ...

    @abstractmethod
    async def get_tournament(self, tournament_id: str) -> Tournament | None: ...

    @abstractmethod
    async def list_tournaments_by_owner(self, owner_user_id: str) -> list[Tournament]: ...

    @abstractmethod
    async def add_game(self, game: TournamentGame) -> None: ...

    @abstractmethod
    async def list_games(self, tournament_id: str) -> list[TournamentGame]: ...

    @abstractmethod
    async def list_unfinished_games(self) -> list[TournamentGame]:
        """
        Return every tournament's games that have no finish yet, oldest first.
        """

    @abstractmethod
    async def finish_game(
        self, game_id: str, *, ended_at: float, end_reason: GameEndReason, result: list[PlayedGameStanding]
    ) -> bool:
        """
        Record a tournament game's finish; return False when the game is unknown or already finished.
        """
