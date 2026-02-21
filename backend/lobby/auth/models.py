"""User model for Starlette AuthenticationMiddleware integration."""

from __future__ import annotations

from starlette.authentication import BaseUser


class AuthenticatedPlayer(BaseUser):
    """Authenticated user for Starlette's request.user.

    Created by the auth backend from either a session cookie or an API key.
    """

    def __init__(self, user_id: str, username: str) -> None:
        self._user_id = user_id
        self._username = username

    @property
    def is_authenticated(self) -> bool:  # pragma: no cover
        return True

    @property
    def display_name(self) -> str:  # pragma: no cover
        return self._username

    @property
    def identity(self) -> str:  # pragma: no cover
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @property
    def user_id(self) -> str:
        return self._user_id
