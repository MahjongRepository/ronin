"""Password hashing utilities using bcrypt.

bcrypt is CPU-bound (~100ms per call). Both functions run the bcrypt
operation off the event loop using anyio.to_thread.run_sync() to avoid
blocking the Starlette event loop under concurrent requests.
"""

import bcrypt
from anyio import to_thread


async def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt. Runs off the event loop."""
    encoded = plain.encode("utf-8")
    return await to_thread.run_sync(lambda: bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8"))


async def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash. Runs off the event loop.

    Returns False for malformed hashes (e.g. corrupted data in the user store)
    rather than propagating a ValueError.
    """
    encoded_plain = plain.encode("utf-8")
    encoded_hash = hashed.encode("utf-8")
    try:
        return await to_thread.run_sync(lambda: bcrypt.checkpw(encoded_plain, encoded_hash))
    except ValueError:
        return False
