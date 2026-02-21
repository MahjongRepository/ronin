"""Authentication and authorization utilities shared between lobby and game services."""

from shared.auth.game_ticket import TICKET_TTL_SECONDS, GameTicket, sign_game_ticket, verify_game_ticket
from shared.auth.models import AccountType, AuthSession, Player
from shared.auth.password import hash_password, verify_password
from shared.auth.service import AuthError, AuthService
from shared.auth.session_store import AuthSessionStore
from shared.auth.settings import AuthSettings

__all__ = [
    "TICKET_TTL_SECONDS",
    "AccountType",
    "AuthError",
    "AuthService",
    "AuthSession",
    "AuthSessionStore",
    "AuthSettings",
    "GameTicket",
    "Player",
    "hash_password",
    "sign_game_ticket",
    "verify_game_ticket",
    "verify_password",
]
