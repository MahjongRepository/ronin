"""Abstract interface for player persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.auth.models import Player


class PlayerRepository(ABC):
    """Abstract interface for player persistence.

    Implementations can use SQLite, PostgreSQL, etc.
    """

    @abstractmethod
    async def create_player(self, player: Player) -> None: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> Player | None: ...

    @abstractmethod
    async def get_by_api_key_hash(self, api_key_hash: str) -> Player | None: ...
