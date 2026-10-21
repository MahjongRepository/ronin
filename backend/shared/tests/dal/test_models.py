from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.dal.models import AccountType, Player


class TestPlayerValidation:
    def test_player__when_human_has_empty_password_hash__should_reject(self):
        with pytest.raises(ValidationError, match="password hash"):
            Player(
                user_id="u1",
                username="alice",
                password_hash="",
                account_type=AccountType.HUMAN,
            )

    def test_player__when_bot_has_no_api_key_hash__should_reject(self):
        with pytest.raises(ValidationError, match="api_key_hash"):
            Player(
                user_id="b1",
                username="bot",
                password_hash="!",
                account_type=AccountType.BOT,
                api_key_hash=None,
            )
