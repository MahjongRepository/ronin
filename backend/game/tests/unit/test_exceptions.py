"""Tests for the domain exception hierarchy."""

from game.logic.exceptions import (
    InvalidGameActionError,
)


class TestInvalidGameActionError:
    """Verify InvalidGameActionError formats its message correctly."""

    def test_message_format(self) -> None:
        err = InvalidGameActionError(action="declare_riichi", seat=0, reason="not tenpai")
        assert str(err) == "invalid declare_riichi from seat 0: not tenpai"
