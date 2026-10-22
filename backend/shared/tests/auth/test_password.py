from __future__ import annotations

from shared.auth.password import BcryptHasher


class TestBcryptHasher:
    async def test_bcrypt_hasher__when_password_matches__should_verify(self):
        hasher = BcryptHasher(rounds=4)
        hashed = await hasher.hash("my-secret-password")
        assert await hasher.verify("my-secret-password", hashed) is True

    async def test_bcrypt_hasher__when_rounds_given__should_hash_at_that_cost(self):
        hashed = await BcryptHasher(rounds=5).hash("my-secret-password")
        assert hashed.startswith("$2b$05$")

    async def test_bcrypt_hasher__when_password_wrong__should_reject(self):
        hasher = BcryptHasher(rounds=4)
        hashed = await hasher.hash("correct-password")
        assert await hasher.verify("wrong-password", hashed) is False

    async def test_bcrypt_hasher__when_hash_malformed__should_return_false(self):
        hasher = BcryptHasher(rounds=4)
        assert await hasher.verify("any-password", "!") is False
        assert await hasher.verify("any-password", "not-a-bcrypt-hash") is False
