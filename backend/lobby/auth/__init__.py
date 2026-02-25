"""Lobby authentication: Starlette backend, user model, and route policy."""

from lobby.auth.backend import SessionOrApiKeyBackend
from lobby.auth.models import AuthenticatedPlayer
from lobby.auth.policy import bot_only, protected_api, protected_html, public_route, validate_route_auth_policy

__all__ = [
    "AuthenticatedPlayer",
    "SessionOrApiKeyBackend",
    "bot_only",
    "protected_api",
    "protected_html",
    "public_route",
    "validate_route_auth_policy",
]
