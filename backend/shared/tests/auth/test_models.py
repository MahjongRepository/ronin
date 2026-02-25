"""Tests for Player model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.auth.models import AccountType, Player


class TestPlayerValidation:
    def test_human_with_empty_password_hash_rejected(self):
        with pytest.raises(ValidationError, match="password hash"):
            Player(
                user_id="u1",
                username="alice",
                password_hash="",
                account_type=AccountType.HUMAN,
            )

    def test_bot_without_api_key_hash_rejected(self):
        with pytest.raises(ValidationError, match="api_key_hash"):
            Player(
                user_id="b1",
                username="bot",
                password_hash="!",
                account_type=AccountType.BOT,
                api_key_hash=None,
            )
