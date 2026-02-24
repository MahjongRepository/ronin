"""Tests for password hashers."""

from __future__ import annotations

import pytest

from shared.auth.password import BcryptHasher, SimpleHasher, get_hasher


class TestBcryptHasher:
    async def test_hash_and_verify_roundtrip(self):
        hasher = BcryptHasher()
        hashed = await hasher.hash("my-secret-password")
        assert await hasher.verify("my-secret-password", hashed) is True

    async def test_wrong_password_rejected(self):
        hasher = BcryptHasher()
        hashed = await hasher.hash("correct-password")
        assert await hasher.verify("wrong-password", hashed) is False

    async def test_malformed_hash_returns_false(self):
        """verify returns False for non-bcrypt hashes instead of raising."""
        hasher = BcryptHasher()
        assert await hasher.verify("any-password", "!") is False
        assert await hasher.verify("any-password", "not-a-bcrypt-hash") is False


class TestSimpleHasher:
    async def test_hash_and_verify_roundtrip(self):
        hasher = SimpleHasher()
        hashed = await hasher.hash("my-secret-password")
        assert await hasher.verify("my-secret-password", hashed) is True

    async def test_wrong_password_rejected(self):
        hasher = SimpleHasher()
        hashed = await hasher.hash("correct-password")
        assert await hasher.verify("wrong-password", hashed) is False

    async def test_rejects_non_simple_hash(self):
        hasher = SimpleHasher()
        assert await hasher.verify("any-password", "not-a-simple-hash") is False


class TestGetHasher:
    def test_returns_bcrypt_by_default(self):
        assert isinstance(get_hasher(), BcryptHasher)

    def test_returns_simple(self):
        assert isinstance(get_hasher("simple"), SimpleHasher)

    def test_raises_for_unknown(self):
        with pytest.raises(ValueError, match="Unknown password hasher"):
            get_hasher("argon2")
