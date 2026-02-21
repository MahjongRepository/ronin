"""Password hashing: protocol, bcrypt (production), and simple SHA-256 (tests).

BcryptHasher is CPU-bound (~100ms per call) and runs off the event loop
using anyio.to_thread.run_sync() to avoid blocking under concurrent requests.

SimpleHasher uses SHA-256 with a "simple$" prefix for instant hashing.
It is intended for tests only.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable

import bcrypt
from anyio import to_thread


@runtime_checkable
class PasswordHasher(Protocol):
    """Hash and verify passwords."""

    async def hash(self, plain: str) -> str: ...

    async def verify(self, plain: str, hashed: str) -> bool: ...


class BcryptHasher:
    """Production hasher using bcrypt (async, off-thread)."""

    async def hash(self, plain: str) -> str:
        encoded = plain.encode("utf-8")
        return await to_thread.run_sync(lambda: bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8"))

    async def verify(self, plain: str, hashed: str) -> bool:
        """Return False for malformed hashes rather than propagating a ValueError."""
        encoded_plain = plain.encode("utf-8")
        encoded_hash = hashed.encode("utf-8")
        try:
            return await to_thread.run_sync(lambda: bcrypt.checkpw(encoded_plain, encoded_hash))
        except ValueError:
            return False


_SIMPLE_PREFIX = "simple$"


class SimpleHasher:
    """Fast SHA-256 hasher for tests. Not suitable for production use."""

    async def hash(self, plain: str) -> str:
        return _SIMPLE_PREFIX + hashlib.sha256(plain.encode("utf-8")).hexdigest()

    async def verify(self, plain: str, hashed: str) -> bool:
        if not hashed.startswith(_SIMPLE_PREFIX):
            return False
        expected = _SIMPLE_PREFIX + hashlib.sha256(plain.encode("utf-8")).hexdigest()
        return hashed == expected


def get_hasher(name: str = "bcrypt") -> PasswordHasher:
    """Return a PasswordHasher by name ("bcrypt" or "simple")."""
    if name == "bcrypt":
        return BcryptHasher()
    if name == "simple":
        return SimpleHasher()
    raise ValueError(f"Unknown password hasher: {name!r}")
