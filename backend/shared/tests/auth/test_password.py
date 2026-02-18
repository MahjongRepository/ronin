"""Tests for password hashing utilities."""

from __future__ import annotations

from shared.auth.password import hash_password, verify_password


class TestPasswordHashing:
    async def test_hash_and_verify_roundtrip(self):
        hashed = await hash_password("my-secret-password")
        assert await verify_password("my-secret-password", hashed) is True

    async def test_wrong_password_rejected(self):
        hashed = await hash_password("correct-password")
        assert await verify_password("wrong-password", hashed) is False

    async def test_malformed_hash_returns_false(self):
        """verify_password returns False for non-bcrypt hashes instead of raising."""
        assert await verify_password("any-password", "!") is False
        assert await verify_password("any-password", "not-a-bcrypt-hash") is False
