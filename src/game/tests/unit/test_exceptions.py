"""Tests for the domain exception hierarchy."""

import pytest

from game.logic.exceptions import (
    GameRuleError,
    InvalidActionError,
    InvalidDiscardError,
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
