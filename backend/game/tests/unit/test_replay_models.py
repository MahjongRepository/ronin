import pytest
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.replay.models import (
    ReplayInput,
    ReplayInputEvent,
)

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")


class TestReplayInputValidation:
    def test_replay_input__when_player_names_duplicate__should_reject(self):
        with pytest.raises(ValidationError, match="4 unique names"):
            ReplayInput(
                seed="a" * 192,
                player_names=("Alice", "Alice", "Bob", "Charlie"),
                events=(),
            )

    def test_replay_input__when_event_names_unknown_player__should_reject(self):
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

    def test_replay_input__when_wall_not_136_tiles__should_reject(self):
        with pytest.raises(ValidationError, match="exactly 136 tiles"):
            ReplayInput(seed="a" * 192, player_names=PLAYER_NAMES, events=(), wall=(1, 2, 3))

    def test_replay_input__when_wall_not_tile_permutation__should_reject(self):
        # Shifted tile IDs (1-136 instead of 0-135)
        with pytest.raises(ValidationError, match="permutation of tile IDs"):
            ReplayInput(seed="a" * 192, player_names=PLAYER_NAMES, events=(), wall=tuple(range(1, 137)))

        # Duplicate tile IDs
        with pytest.raises(ValidationError, match="permutation of tile IDs"):
            ReplayInput(seed="a" * 192, player_names=PLAYER_NAMES, events=(), wall=(0,) * 136)
