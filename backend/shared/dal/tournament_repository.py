from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.dal.models import Tournament


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
