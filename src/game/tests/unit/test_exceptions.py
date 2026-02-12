"""Tests for the domain exception hierarchy."""

import pytest

from game.logic.exceptions import (
    GameRuleError,
    InvalidActionError,
    InvalidDiscardError,
    InvalidGameActionError,
    InvalidMeldError,
    InvalidRiichiError,
    InvalidWinError,
)


class TestGameRuleErrorHierarchy:
    """Verify all domain exception subclasses inherit from GameRuleError."""

    def test_invalid_discard_is_game_rule_error(self) -> None:
        err = InvalidDiscardError("test")
        assert isinstance(err, GameRuleError)

    def test_invalid_meld_is_game_rule_error(self) -> None:
        err = InvalidMeldError("test")
        assert isinstance(err, GameRuleError)

    def test_invalid_riichi_is_game_rule_error(self) -> None:
        err = InvalidRiichiError("test")
        assert isinstance(err, GameRuleError)

    def test_invalid_win_is_game_rule_error(self) -> None:
        err = InvalidWinError("test")
        assert isinstance(err, GameRuleError)

    def test_invalid_action_is_game_rule_error(self) -> None:
        err = InvalidActionError("test")
        assert isinstance(err, GameRuleError)

    def test_catch_base_catches_all_subclasses(self) -> None:
        """Catching GameRuleError catches all subclasses."""
        for exc_class in (
            InvalidDiscardError,
            InvalidMeldError,
            InvalidRiichiError,
            InvalidWinError,
            InvalidActionError,
        ):
            with pytest.raises(GameRuleError, match="test message"):
                raise exc_class("test message")

    def test_message_preserved(self) -> None:
        err = InvalidDiscardError("cannot discard: kuikae restriction")
        assert str(err) == "cannot discard: kuikae restriction"


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

    def test_not_a_game_rule_error(self) -> None:
        """InvalidGameActionError is a standalone Exception, not a GameRuleError subclass."""
        err = InvalidGameActionError(action="discard", seat=1, reason="test")
        assert not isinstance(err, GameRuleError)
        assert isinstance(err, Exception)

    def test_requires_keyword_arguments(self) -> None:
        with pytest.raises(TypeError):
            InvalidGameActionError("discard", 0, "reason")  # type: ignore[misc]
