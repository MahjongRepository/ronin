"""Auth service coordinating registration, login, and session management."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING
from uuid import uuid4

from shared.auth.models import AccountType, User
from shared.auth.password import hash_password, verify_password

if TYPE_CHECKING:
    from shared.auth.models import AuthSession
    from shared.auth.repository import UserRepository
    from shared.auth.session_store import AuthSessionStore

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt truncates at 72 bytes


class AuthError(Exception):
    """Authentication or authorization failure."""


class AuthService:
    """Coordinate user registration, login, and session validation."""

    def __init__(self, user_repo: UserRepository, session_store: AuthSessionStore | None = None) -> None:
        self._user_repo = user_repo
        self._session_store = session_store

    async def register(self, username: str, password: str) -> User:
        """Register a new human user account."""
        _validate_username(username)
        _validate_password(password)
        await self._ensure_username_available(username)

        password_hashed = await hash_password(password)
        user = User(
            user_id=str(uuid4()),
            username=username,
            password_hash=password_hashed,
            account_type=AccountType.HUMAN,
        )
        return await self._save_user(user)

    async def login(self, username: str, password: str) -> AuthSession:
        """Validate credentials and create a session. Reject bot accounts."""
        store = self._require_session_store()
        user = await self._user_repo.get_by_username(username)
        if user is None:
            raise AuthError("Invalid credentials")
        if user.account_type == AccountType.BOT:
            raise AuthError("Invalid credentials")
        if not await verify_password(password, user.password_hash):
            raise AuthError("Invalid credentials")
        return store.create_session(user.user_id, user.username)

    def validate_session(self, session_id: str | None) -> AuthSession | None:
        """Return the session if valid and not expired, otherwise None."""
        store = self._require_session_store()
        if session_id is None:
            return None
        return store.get_session(session_id)

    def logout(self, session_id: str) -> None:
        """Destroy a session."""
        self._require_session_store().delete_session(session_id)

    async def validate_api_key(self, api_key: str) -> User | None:
        """Validate a bot API key by hashing and looking up the hash."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return await self._user_repo.get_by_api_key_hash(key_hash)

    # -- private helpers --

    def _require_session_store(self) -> AuthSessionStore:
        if self._session_store is None:
            raise RuntimeError("session_store is required for session operations")
        return self._session_store

    async def _ensure_username_available(self, username: str) -> None:
        """Raise AuthError if the username is already taken."""
        if await self._user_repo.get_by_username(username) is not None:
            raise AuthError(f"Username '{username}' is already taken")

    async def _save_user(self, user: User) -> User:
        """Persist a user via the repository, wrapping ValueError into AuthError."""
        try:
            await self._user_repo.create_user(user)
        except ValueError as e:
            raise AuthError(str(e)) from e
        return user


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
