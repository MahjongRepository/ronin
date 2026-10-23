from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.authentication import AuthCredentials, AuthenticationBackend

from lobby.auth.models import AuthenticatedPlayer
from shared.dal.models import AccountType

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection

    from shared.auth.service import AuthService


class SessionOrApiKeyBackend(AuthenticationBackend):
    """
    Authenticate requests via the session cookie or the X-API-Key header.

    Checks the session cookie first. If it is absent or invalid, falls back to the X-API-Key header for bot accounts.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._auth_service = auth_service

    async def authenticate(
        self,
        conn: HTTPConnection,
    ) -> tuple[AuthCredentials, AuthenticatedPlayer] | None:
        session = self._auth_service.validate_session(conn.cookies.get("session_id"))
        if session is not None:
            return AuthCredentials(["authenticated"]), AuthenticatedPlayer(
                user_id=session.user_id,
                username=session.username,
            )

        api_key = conn.headers.get("x-api-key")
        if api_key:
            player = await self._auth_service.validate_api_key(api_key)
            if player is not None and player.account_type == AccountType.BOT:
                return AuthCredentials(["authenticated"]), AuthenticatedPlayer(
                    user_id=player.user_id,
                    username=player.username,
                    account_type=player.account_type,
                )

        return None
