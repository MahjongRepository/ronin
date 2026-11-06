from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

    from shared.dal.models import AuthSession


class SessionRepository(ABC):
    """
    Abstract interface for lobby session persistence.

    Every operation takes the current time as `now`: a row whose `expires_at` is not after `now` is expired.
    """

    @abstractmethod
    async def create(self, session: AuthSession, *, now: float, replacing_token_hash: str | None) -> None: ...

    @abstractmethod
    async def create_guest(  # noqa: PLR0913
        self,
        *,
        token_hash: str,
        user_id: str,
        created_at: float,
        expires_at: float,
        now: float,
        pick_name: Callable[[Collection[str]], str],
        replacing_token_hash: str | None,
    ) -> AuthSession: ...

    @abstractmethod
    async def get(self, token_hash: str, *, now: float) -> AuthSession | None: ...

    @abstractmethod
    async def delete(self, token_hash: str) -> None: ...
