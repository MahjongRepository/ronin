"""Tests for the domain exception hierarchy."""

import pytest

from game.logic.exceptions import (
    InvalidGameActionError,
)


class TestInvalidGameActionError:
    """Verify InvalidGameActionError stores action context and is NOT a GameRuleError."""

    def test_stores_action_seat_reason(self) -> None:
        err = InvalidGameActionError(action="discard", seat=2, reason="tile not in hand")
        assert err.action == "discard"
        assert err.seat == 2
        assert err.reason == "tile not in hand"

    def test_message_format(self) -> None:
        err = InvalidGameActionError(action="declare_riichi", seat=0, reason="not tenpai")
        assert str(err) == "invalid declare_riichi from seat 0: not tenpai"

    def test_requires_keyword_arguments(self) -> None:
        with pytest.raises(TypeError):
            InvalidGameActionError("discard", 0, "reason")  # type: ignore[misc]
