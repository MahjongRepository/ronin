"""Starlette AuthenticationBackend that validates session cookies or API keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.authentication import AuthCredentials, AuthenticationBackend

from lobby.auth.models import AuthenticatedPlayer
from shared.auth.models import AccountType

if TYPE_CHECKING:
    from starlette.requests import HTTPConnection

    from shared.auth.service import AuthService


class SessionOrApiKeyBackend(AuthenticationBackend):
    """Authenticate requests via session cookie/query param or X-API-Key header.

    Checks the session cookie first, then the ``session_id`` query parameter
    (used by WebSocket clients). If both are absent or invalid, falls back to
    the X-API-Key header for bot accounts.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._auth_service = auth_service

    async def authenticate(
        self,
        conn: HTTPConnection,
    ) -> tuple[AuthCredentials, AuthenticatedPlayer] | None:
        # Check cookie first, then fall back to query param (WebSocket only).
        session_id = conn.cookies.get("session_id")
        if session_id is None and conn.scope["type"] == "websocket":
            session_id = conn.query_params.get("session_id")
        session = self._auth_service.validate_session(session_id)
        if session is not None:
            return AuthCredentials(["authenticated"]), AuthenticatedPlayer(
                user_id=session.user_id,
                username=session.username,
                account_type=session.account_type,
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
