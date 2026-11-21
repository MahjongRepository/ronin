from __future__ import annotations

from typing import Protocol, runtime_checkable

import bcrypt
from anyio import to_thread


@runtime_checkable
class PasswordHasher(Protocol):
    """
    Hash and verify passwords.
    """

    async def hash(self, plain: str) -> str: ...

    async def verify(self, plain: str, hashed: str) -> bool: ...


class BcryptHasher:
    """
    Hash passwords with bcrypt at the given cost (async, off-thread).
    """

    def __init__(self, rounds: int) -> None:
        self._rounds = rounds

    async def hash(self, plain: str) -> str:
        encoded = plain.encode("utf-8")
        salt = bcrypt.gensalt(rounds=self._rounds)
        return await to_thread.run_sync(lambda: bcrypt.hashpw(encoded, salt).decode("utf-8"))

    async def verify(self, plain: str, hashed: str) -> bool:
        """
        Return False for malformed hashes rather than propagating a ValueError.
        """
        encoded_plain = plain.encode("utf-8")
        encoded_hash = hashed.encode("utf-8")
        try:
            return await to_thread.run_sync(lambda: bcrypt.checkpw(encoded_plain, encoded_hash))
        except ValueError:
            return False
