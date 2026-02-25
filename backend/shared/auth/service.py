"""Auth service coordinating registration, login, and session management."""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import TYPE_CHECKING
from uuid import uuid4

from shared.auth.models import AccountType, Player

if TYPE_CHECKING:
    from shared.auth.models import AuthSession
    from shared.auth.password import PasswordHasher
    from shared.auth.session_store import AuthSessionStore
    from shared.dal.player_repository import PlayerRepository

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt truncates at 72 bytes


class AuthError(Exception):
    """Authentication or authorization failure."""


class AuthService:
    """Coordinate player registration, login, and session validation."""

    def __init__(
        self,
        player_repo: PlayerRepository,
        session_store: AuthSessionStore | None = None,
        *,
        password_hasher: PasswordHasher,
    ) -> None:
        self._player_repo = player_repo
        self._session_store = session_store
        self._hasher = password_hasher

    async def register(self, username: str, password: str) -> Player:
        """Register a new human player account."""
        _validate_username(username)
        _validate_password(password)
        await self._ensure_username_available(username)

        password_hashed = await self._hasher.hash(password)
        player = Player(
            user_id=str(uuid4()),
            username=username,
            password_hash=password_hashed,
            account_type=AccountType.HUMAN,
        )
        return await self._save_player(player)

    async def register_bot(self, bot_name: str) -> tuple[Player, str]:  # deadcode: ignore
        """Register a bot account and return (player, raw_api_key).

        Validates username rules, generates a random API key,
        hashes it with SHA-256, and persists the bot player.
        The raw API key is returned once and never stored.
        """
        _validate_username(bot_name)
        await self._ensure_username_available(bot_name)

        raw_api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
        player = Player(
            user_id=str(uuid4()),
            username=bot_name,
            password_hash="!",  # noqa: S106 - sentinel for bot accounts (no password login)
            account_type=AccountType.BOT,
            api_key_hash=api_key_hash,
        )
        saved = await self._save_player(player)
        return saved, raw_api_key

    async def login(self, username: str, password: str) -> AuthSession:
        """Validate credentials and create a session. Reject bot accounts."""
        store = self._require_session_store()
        player = await self._player_repo.get_by_username(username)
        if player is None:
            raise AuthError("Invalid credentials")
        if player.account_type == AccountType.BOT:
            raise AuthError("Invalid credentials")
        if not await self._hasher.verify(password, player.password_hash):
            raise AuthError("Invalid credentials")
        return store.create_session(player.user_id, player.username, account_type=AccountType.HUMAN)

    def validate_session(self, session_id: str | None) -> AuthSession | None:
        """Return the session if valid and not expired, otherwise None."""
        store = self._require_session_store()
        if session_id is None:
            return None
        return store.get_session(session_id)

    def create_session(
        self,
        user_id: str,
        username: str,
        account_type: AccountType = AccountType.HUMAN,
    ) -> AuthSession:
        """Create a session for an authenticated user (e.g., bot after API key validation)."""
        return self._require_session_store().create_session(user_id, username, account_type=account_type)

    def logout(self, session_id: str) -> None:
        """Destroy a session."""
        self._require_session_store().delete_session(session_id)

    async def validate_api_key(self, api_key: str) -> Player | None:
        """Validate a bot API key by hashing and looking up the hash."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return await self._player_repo.get_by_api_key_hash(key_hash)

    # -- private helpers --

    def _require_session_store(self) -> AuthSessionStore:
        if self._session_store is None:
            raise RuntimeError("session_store is required for session operations")
        return self._session_store

    async def _ensure_username_available(self, username: str) -> None:
        """Raise AuthError if the username is already taken."""
        if await self._player_repo.get_by_username(username) is not None:
            raise AuthError(f"Username '{username}' is already taken")

    async def _save_player(self, player: Player) -> Player:
        """Persist a player via the repository, wrapping ValueError into AuthError."""
        try:
            await self._player_repo.create_player(player)
        except ValueError as e:
            raise AuthError(str(e)) from e
        return player


def _validate_username(username: str) -> None:
    """Validate username: 3-30 chars, alphanumeric + underscores."""
    if len(username) < USERNAME_MIN_LENGTH or len(username) > USERNAME_MAX_LENGTH:
        raise AuthError(f"Username must be between {USERNAME_MIN_LENGTH} and {USERNAME_MAX_LENGTH} characters")
    if not USERNAME_PATTERN.match(username):
        raise AuthError("Username must contain only letters, numbers, and underscores")


def _validate_password(password: str) -> None:
    """Validate password: 8-72 chars, max 72 UTF-8 bytes (bcrypt limit)."""
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise AuthError(f"Password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters")
    if len(password.encode("utf-8")) > PASSWORD_MAX_LENGTH:
        raise AuthError(f"Password must not exceed {PASSWORD_MAX_LENGTH} bytes when encoded")
