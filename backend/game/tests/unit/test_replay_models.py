"""Tests for replay model validation."""

import pytest
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.replay.models import (
    ReplayInput,
    ReplayInputEvent,
)

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")


class TestReplayInputValidation:
    """Tests for ReplayInput model_validator constraints."""

    def test_rejects_duplicate_names(self):
        with pytest.raises(ValidationError, match="4 unique names"):
            ReplayInput(
                seed="a" * 192,
                player_names=("Alice", "Alice", "Bob", "Charlie"),
                events=(),
            )

    def test_rejects_unknown_player_in_events(self):
        with pytest.raises(ValidationError, match="unknown player_name"):
            ReplayInput(
                seed="a" * 192,
                player_names=PLAYER_NAMES,
                events=(
                    ReplayInputEvent(
                        player_name="UnknownPlayer",
                        action=GameAction.DISCARD,
                    ),
                ),
            )

    def test_rejects_wall_wrong_length(self):
        with pytest.raises(ValidationError, match="exactly 136 tiles"):
            ReplayInput(seed="a" * 192, player_names=PLAYER_NAMES, events=(), wall=(1, 2, 3))

    def test_rejects_invalid_wall(self):
        # Shifted tile IDs (1-136 instead of 0-135)
        with pytest.raises(ValidationError, match="permutation of tile IDs"):
            ReplayInput(seed="a" * 192, player_names=PLAYER_NAMES, events=(), wall=tuple(range(1, 137)))
        # Duplicate tile IDs
        with pytest.raises(ValidationError, match="permutation of tile IDs"):
            ReplayInput(seed="a" * 192, player_names=PLAYER_NAMES, events=(), wall=(0,) * 136)
