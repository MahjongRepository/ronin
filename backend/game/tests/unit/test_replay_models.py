"""Tests for replay model validation."""

import pytest
from pydantic import ValidationError

from game.logic.enums import GameAction, GameErrorCode
from game.logic.events import (
    BroadcastTarget,
    ErrorEvent,
    EventType,
    ServiceEvent,
)
from game.replay.models import (
    ReplayError,
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


class TestReplayError:
    def test_message_includes_error_count(self):
        error_event = ServiceEvent(
            event=EventType.ERROR,
            data=ErrorEvent(
                code=GameErrorCode.GAME_ERROR,
                message="test error message",
                target="all",
            ),
            target=BroadcastTarget(),
        )
        input_event = ReplayInputEvent(player_name="Alice", action=GameAction.DISCARD, data={"tile_id": 0})
        exc = ReplayError(step_index=5, event=input_event, errors=[error_event])
        assert "1 error(s)" in str(exc)
        assert "test error message" in str(exc)
        assert "step 5" in str(exc)
        assert "Alice" in str(exc)

    def test_message_with_multiple_errors(self):
        errors = [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.GAME_ERROR,
                    message=f"error {i}",
                    target="all",
                ),
                target=BroadcastTarget(),
            )
            for i in range(3)
        ]
        input_event = ReplayInputEvent(player_name="Bob", action=GameAction.CALL_RON)
        exc = ReplayError(step_index=0, event=input_event, errors=errors)
        assert "3 error(s)" in str(exc)
