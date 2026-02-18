"""Abstract interface for user persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.auth.models import User


class UserRepository(ABC):
    """Abstract interface for user persistence.

    Implementations can use files, SQLite, PostgreSQL, etc.
    """

    @abstractmethod
    async def create_user(self, user: User) -> None: ...

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None: ...

    @abstractmethod
    async def get_by_api_key_hash(self, api_key_hash: str) -> User | None: ...
