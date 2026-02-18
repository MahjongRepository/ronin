"""File-backed user repository storing users as JSON."""

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path

from shared.auth.models import User
from shared.auth.repository import UserRepository

logger = logging.getLogger(__name__)

_FILE_PERMISSIONS = 0o600  # owner read/write only


class FileUserRepository(UserRepository):
    """File-backed user repository.

    Stores users as JSON in a single file. Loads into memory on startup,
    writes back on mutation. Uses asyncio.Lock for write safety within a
    single process.

    Limitation: only supports a single lobby instance. Multiple instances
    would cause write conflicts. The abstract UserRepository interface allows
    swapping to SQLite/PostgreSQL later for multi-instance support.
    """

    def __init__(self, file_path: str | Path) -> None:
        self._file_path = Path(file_path)
        self._users: dict[str, User] = {}  # keyed by user_id
        self._lock = asyncio.Lock()
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """Load users from file on first access."""
        async with self._lock:
            if self._loaded:
                return
            self._load_from_file()
            self._loaded = True

    def _load_from_file(self) -> None:
        """Load users from the JSON file into memory.

        Starts with an empty store when the file does not exist yet.
        Raises on read/parse failures for an existing file to prevent
        data loss from overwriting a file we could not read.
        """
        self._users = {}

        if not self._file_path.exists():
            return

        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            msg = f"Failed to load users from {self._file_path}"
            raise OSError(msg) from exc

        if not isinstance(data, dict):
            msg = f"Expected JSON object at root in {self._file_path}"
            raise OSError(msg)

        try:
            self._users = {uid: User.model_validate(user_data) for uid, user_data in data.items()}
        except ValueError as exc:
            msg = f"Failed to parse user data from {self._file_path}"
            raise OSError(msg) from exc

    def _save_to_file(self) -> None:
        """Atomically write all users to the JSON file.

        Writes to a temporary file in the same directory, then renames
        into place so readers never see a partial/truncated file.
        Sets restrictive permissions (owner-only) since the file
        contains password and API-key hashes.
        """
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {uid: user.model_dump() for uid, user in self._users.items()}
        content = json.dumps(data, indent=2).encode("utf-8")

        fd, tmp_path = tempfile.mkstemp(
            dir=self._file_path.parent,
            prefix=".users_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fchmod(f.fileno(), _FILE_PERMISSIONS)
            Path(tmp_path).replace(self._file_path)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()
            raise

    async def create_user(self, user: User) -> None:
        """Add a user. Raises ValueError if user_id or username already exists."""
        await self._ensure_loaded()
        async with self._lock:
            if user.user_id in self._users:
                raise ValueError(f"User with id '{user.user_id}' already exists")
            for existing in self._users.values():
                if existing.username.lower() == user.username.lower():
                    raise ValueError(f"Username '{user.username}' already taken")
            self._users[user.user_id] = user
            try:
                self._save_to_file()
            except OSError:
                del self._users[user.user_id]
                raise

    async def get_by_username(self, username: str) -> User | None:
        """Look up a user by username (case-insensitive)."""
        await self._ensure_loaded()
        lower = username.lower()
        return next((u for u in self._users.values() if u.username.lower() == lower), None)

    async def get_by_api_key_hash(self, api_key_hash: str) -> User | None:
        """Look up a user by API key hash."""
        await self._ensure_loaded()
        return next((u for u in self._users.values() if u.api_key_hash == api_key_hash), None)
