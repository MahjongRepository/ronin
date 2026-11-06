from __future__ import annotations

import hashlib
import re
import secrets
import time
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from shared.dal.models import AccountType, AuthSession, Player

if TYPE_CHECKING:
    from collections.abc import Collection

    from shared.auth.password import PasswordHasher
    from shared.dal.player_repository import PlayerRepository
    from shared.dal.session_repository import SessionRepository

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt truncates at 72 bytes

GUEST_NAME_PREFIX = "Nanashi-"
GUEST_NAMES = tuple(f"{GUEST_NAME_PREFIX}{n}" for n in range(1000, 10000))

ACCOUNT_SESSION_IDLE_SECONDS = 30 * 86400
GUEST_SESSION_IDLE_SECONDS = 7 * 86400
SESSION_MAX_AGE_SECONDS = 90 * 86400
SESSION_RENEWAL_INTERVAL_SECONDS = 86400


class AuthErrorCode(StrEnum):
    WRONG_CREDENTIALS = "wrong_credentials"
    USERNAME_TAKEN = "username_taken"
    USERNAME_LENGTH = "username_length"
    USERNAME_PATTERN = "username_pattern"
    PASSWORD_LENGTH = "password_length"  # noqa: S105 - an error code, not a password
    PASSWORD_BYTES = "password_bytes"  # noqa: S105 - an error code, not a password
    HUMAN_ACCOUNT = "human_account"
    ACCOUNT_NOT_SAVED = "account_not_saved"


class AuthError(Exception):
    """
    Authentication or authorization failure.

    ``code`` and ``params`` name the failure for a page to word in its own language; the message stays English for the
    bot registration script and the logs.
    """

    def __init__(self, code: AuthErrorCode, message: str, **params: str | int) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


class AuthService:
    """
    Coordinate player registration, login, and session validation.
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        session_repo: SessionRepository,
        *,
        password_hasher: PasswordHasher,
    ) -> None:
        self._player_repo = player_repo
        self._session_repo = session_repo
        self._hasher = password_hasher

    async def register(self, username: str, password: str) -> Player:
        """
        Register a new human player account.
        """
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

    async def register_bot(self, bot_name: str) -> tuple[Player, str]:
        """
        Register a bot account and return (player, raw_api_key).

        Validates username rules, generates a random API key, hashes it with SHA-256, and persists the bot player. The
        raw API key is returned once and never stored.
        """
        _validate_username(bot_name)
        await self._ensure_username_available(bot_name)

        raw_api_key, api_key_hash = _generate_token()
        player = Player(
            user_id=str(uuid4()),
            username=bot_name,
            password_hash="!",  # noqa: S106 - sentinel for bot accounts (no password login)
            account_type=AccountType.BOT,
            api_key_hash=api_key_hash,
        )
        saved = await self._save_player(player)
        return saved, raw_api_key

    async def issue_bot_api_key(self, bot_name: str) -> tuple[Player, str]:
        """
        Return the bot account named bot_name with a fresh API key as (player, raw_api_key), registering it if missing.

        The new key replaces the account's previous one, which stops working.
        """
        player = await self._player_repo.get_by_username(bot_name)
        if player is None:
            return await self.register_bot(bot_name)

        if player.account_type != AccountType.BOT:
            raise AuthError(
                AuthErrorCode.HUMAN_ACCOUNT, f"Username '{bot_name}' belongs to a human account", username=bot_name
            )

        raw_api_key, api_key_hash = _generate_token()
        try:
            await self._player_repo.set_api_key_hash(player.user_id, api_key_hash)
        except ValueError as e:
            raise AuthError(AuthErrorCode.ACCOUNT_NOT_SAVED, str(e)) from e

        return player.model_copy(update={"api_key_hash": api_key_hash}), raw_api_key

    async def login(self, username: str, password: str, *, replacing: str | None = None) -> tuple[AuthSession, str]:
        """
        Validate credentials and create a session, returned as (session, raw_token).

        Reject bot accounts. The session of the token `replacing` (the incoming cookie), if any, is deleted.
        """
        player = await self._player_repo.get_by_username(username)
        if player is None:
            raise AuthError(AuthErrorCode.WRONG_CREDENTIALS, "Wrong username or password.")

        if player.account_type == AccountType.BOT:
            raise AuthError(AuthErrorCode.WRONG_CREDENTIALS, "Wrong username or password.")

        if not await self._hasher.verify(password, player.password_hash):
            raise AuthError(AuthErrorCode.WRONG_CREDENTIALS, "Wrong username or password.")

        token, token_hash = _generate_token()
        now = time.time()
        session = AuthSession(
            token_hash=token_hash,
            user_id=player.user_id,
            username=player.username,
            is_guest=False,
            created_at=now,
            expires_at=_session_expiry(created_at=now, now=now, is_guest=False),
        )
        await self._session_repo.create(session, now=now, replacing_token_hash=_hash_optional_token(replacing))
        return session, token

    async def login_as_guest(self, *, replacing: str | None = None) -> tuple[AuthSession, str]:
        """
        Create a session for a one-time guest, returned as (session, raw_token): a fresh user id, a generated name and
        no account.

        Picking the name and inserting the session run in one write transaction, so two concurrent guest logins cannot
        take the same name. The session of the token `replacing`, if any, is deleted.
        """
        token, token_hash = _generate_token()
        now = time.time()
        session = await self._session_repo.create_guest(
            token_hash=token_hash,
            user_id=str(uuid4()),
            created_at=now,
            expires_at=_session_expiry(created_at=now, now=now, is_guest=True),
            now=now,
            pick_name=_pick_guest_name,
            replacing_token_hash=_hash_optional_token(replacing),
        )
        return session, token

    async def validate_session(self, token: str | None) -> AuthSession | None:
        """
        Return the session of this token if valid and not expired, otherwise None.

        A valid session slides its expiry to the idle timeout from now, never past the absolute cap. The renewal
        write is batched: it happens only once the expiry has fallen a renewal interval behind.
        """
        if token is None:
            return None

        token_hash = _hash_token(token)
        now = time.time()
        session = await self._session_repo.get(token_hash, now=now)
        if session is None:
            return None

        target = _session_expiry(created_at=session.created_at, now=now, is_guest=session.is_guest)
        renewal_due = (
            session.expires_at < now + _idle_seconds(is_guest=session.is_guest) - SESSION_RENEWAL_INTERVAL_SECONDS
        )
        if target > session.expires_at and renewal_due:
            if not await self._session_repo.extend(token_hash, expires_at=target, now=now):
                return None
            return session.model_copy(update={"expires_at": target})

        return session

    async def logout(self, token: str) -> None:
        """
        Delete the session of this token.
        """
        await self._session_repo.delete(_hash_token(token))

    async def validate_api_key(self, api_key: str) -> Player | None:
        """
        Validate a bot API key by hashing and looking up the hash.
        """
        return await self._player_repo.get_by_api_key_hash(_hash_token(api_key))

    async def is_admin(self, *, user_id: str, username: str) -> bool:
        """
        Return whether the account named username, with this user id, holds the admin flag.

        A guest has no account and is never an admin.
        """
        player = await self._player_repo.get_by_username(username)
        return player is not None and player.user_id == user_id and player.is_admin

    # -- private helpers --

    async def _ensure_username_available(self, username: str) -> None:
        """
        Raise AuthError if the username is already taken.
        """
        if await self._player_repo.get_by_username(username) is not None:
            raise AuthError(AuthErrorCode.USERNAME_TAKEN, f"Username '{username}' is already taken", username=username)

    async def _save_player(self, player: Player) -> Player:
        """
        Persist a player via the repository, wrapping ValueError into AuthError.
        """
        try:
            await self._player_repo.create_player(player)
        except ValueError as e:
            raise AuthError(AuthErrorCode.ACCOUNT_NOT_SAVED, str(e)) from e

        return player


def _generate_token() -> tuple[str, str]:
    """
    Generate a random 256-bit token and return (raw_token, sha256_hex), for API keys and session cookies alike.
    """
    token = secrets.token_urlsafe(32)
    return token, _hash_token(token)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_optional_token(token: str | None) -> str | None:
    return None if token is None else _hash_token(token)


def _idle_seconds(*, is_guest: bool) -> int:
    return GUEST_SESSION_IDLE_SECONDS if is_guest else ACCOUNT_SESSION_IDLE_SECONDS


def _session_expiry(*, created_at: float, now: float, is_guest: bool) -> float:
    """
    Return the expiry a session used at `now` slides to: the idle timeout from now, capped at the absolute maximum age.
    """
    return min(now + _idle_seconds(is_guest=is_guest), created_at + SESSION_MAX_AGE_SECONDS)


def _validate_username(username: str) -> None:
    """
    Validate username: 3-30 chars, alphanumeric + underscores.
    """
    if len(username) < USERNAME_MIN_LENGTH or len(username) > USERNAME_MAX_LENGTH:
        raise AuthError(
            AuthErrorCode.USERNAME_LENGTH,
            f"Username must be between {USERNAME_MIN_LENGTH} and {USERNAME_MAX_LENGTH} characters",
            min=USERNAME_MIN_LENGTH,
            max=USERNAME_MAX_LENGTH,
        )

    if not USERNAME_PATTERN.match(username):
        raise AuthError(AuthErrorCode.USERNAME_PATTERN, "Username must contain only letters, numbers, and underscores")


def _pick_guest_name(taken: Collection[str]) -> str:
    """
    Pick a random guest name that no live guest session holds.

    Unlike a room name, a repeat is harmful: `POST /games` rejects a table with duplicate player names, so with every
    name held this raises instead of reusing one.
    """
    free = [name for name in GUEST_NAMES if name not in taken]
    return secrets.choice(free)


def _validate_password(password: str) -> None:
    """
    Validate password: 8-72 chars, max 72 UTF-8 bytes (bcrypt limit).
    """
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise AuthError(
            AuthErrorCode.PASSWORD_LENGTH,
            f"Password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters",
            min=PASSWORD_MIN_LENGTH,
            max=PASSWORD_MAX_LENGTH,
        )

    if len(password.encode("utf-8")) > PASSWORD_MAX_LENGTH:
        raise AuthError(
            AuthErrorCode.PASSWORD_BYTES,
            f"Password must not exceed {PASSWORD_MAX_LENGTH} bytes when encoded",
            max=PASSWORD_MAX_LENGTH,
        )
