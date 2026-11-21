from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.authentication import AuthCredentials, AuthenticationBackend

from app.auth.models import AuthenticatedPlayer

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection

    from app.auth.service import AuthService


API_KEY_SCOPE = "api_key"


class SessionOrApiKeyBackend(AuthenticationBackend):
    """
    Authenticate requests via the session cookie or the X-API-Key header.

    Checks the session cookie first. If it is absent or invalid, falls back to the X-API-Key header of any account, bot
    or human, and adds the ``api_key`` scope so handlers and policies can tell key auth from cookie auth.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._auth_service = auth_service

    async def authenticate(
        self,
        conn: HTTPConnection,
    ) -> tuple[AuthCredentials, AuthenticatedPlayer] | None:
        session = await self._auth_service.validate_session(conn.cookies.get("session_id"))
        if session is not None:
            return AuthCredentials(["authenticated"]), AuthenticatedPlayer(
                user_id=session.user_id,
                username=session.username,
                credential_hash=session.token_hash,
                is_guest=session.is_guest,
            )

        api_key = conn.headers.get("x-api-key")
        if api_key:
            player = await self._auth_service.validate_api_key(api_key)
            if player is not None and player.api_key_hash is not None:
                return AuthCredentials(["authenticated", API_KEY_SCOPE]), AuthenticatedPlayer(
                    user_id=player.user_id,
                    username=player.username,
                    account_type=player.account_type,
                    credential_hash=player.api_key_hash,
                )

        return None
