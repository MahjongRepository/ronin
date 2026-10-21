from __future__ import annotations

import pytest

from shared.auth.password import BcryptHasher, SimpleHasher, get_hasher


class TestBcryptHasher:
    async def test_bcrypt_hasher__when_password_matches__should_verify(self):
        hasher = BcryptHasher()
        hashed = await hasher.hash("my-secret-password")
        assert await hasher.verify("my-secret-password", hashed) is True

    async def test_bcrypt_hasher__when_password_wrong__should_reject(self):
        hasher = BcryptHasher()
        hashed = await hasher.hash("correct-password")
        assert await hasher.verify("wrong-password", hashed) is False

    async def test_bcrypt_hasher__when_hash_malformed__should_return_false(self):
        hasher = BcryptHasher()
        assert await hasher.verify("any-password", "!") is False
        assert await hasher.verify("any-password", "not-a-bcrypt-hash") is False


class TestSimpleHasher:
    async def test_simple_hasher__when_password_matches__should_verify(self):
        hasher = SimpleHasher()
        hashed = await hasher.hash("my-secret-password")
        assert await hasher.verify("my-secret-password", hashed) is True

    async def test_simple_hasher__when_password_wrong__should_reject(self):
        hasher = SimpleHasher()
        hashed = await hasher.hash("correct-password")
        assert await hasher.verify("wrong-password", hashed) is False

    async def test_simple_hasher__when_hash_not_simple__should_reject(self):
        hasher = SimpleHasher()
        assert await hasher.verify("any-password", "not-a-simple-hash") is False


class TestGetHasher:
    def test_get_hasher__when_no_name__should_return_bcrypt(self):
        assert isinstance(get_hasher(), BcryptHasher)

    def test_get_hasher__when_simple__should_return_simple_hasher(self):
        assert isinstance(get_hasher("simple"), SimpleHasher)

    def test_get_hasher__when_unknown_name__should_raise(self):
        with pytest.raises(ValueError, match="Unknown password hasher"):
            get_hasher("argon2")
