"""Tests for replay model validation and construction."""

import pytest
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.messaging.events import (
    DiscardEvent,
    EventType,
    ServiceEvent,
)
from game.replay.models import (
    ReplayInput,
    ReplayInputEvent,
    ReplayStep,
    ReplayTrace,
)
from game.tests.conftest import create_game_state

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")


class TestReplayInputEvent:
    def test_basic_construction(self):
        event = ReplayInputEvent(
            player_name="Alice",
            action=GameAction.DISCARD,
            data={"tile_id": 5},
        )
        assert event.player_name == "Alice"
        assert event.action == GameAction.DISCARD
        assert event.data == {"tile_id": 5}

    def test_default_empty_data(self):
        event = ReplayInputEvent(
            player_name="Alice",
            action=GameAction.CONFIRM_ROUND,
        )
        assert event.data == {}

    def test_frozen(self):
        event = ReplayInputEvent(player_name="Alice", action=GameAction.DISCARD)
        with pytest.raises(ValidationError):
            event.player_name = "Bob"


class TestReplayInput:
    def test_valid_4_players(self):
        replay = ReplayInput(
            seed=42.0,
            player_names=PLAYER_NAMES,
            events=(),
        )
        assert replay.player_names == PLAYER_NAMES
        assert replay.schema_version == 1

    def test_rejects_duplicate_names(self):
        with pytest.raises(ValidationError, match="4 unique names"):
            ReplayInput(
                seed=1.0,
                player_names=("Alice", "Alice", "Bob", "Charlie"),
                events=(),
            )

    def test_rejects_fewer_than_4_names(self):
        with pytest.raises(ValidationError):
            ReplayInput(
                seed=1.0,
                player_names=("Alice", "Bob", "Charlie"),  # type: ignore[arg-type]
                events=(),
            )

    def test_rejects_more_than_4_names(self):
        with pytest.raises(ValidationError):
            ReplayInput(
                seed=1.0,
                player_names=("A", "B", "C", "D", "E"),  # type: ignore[arg-type]
                events=(),
            )

    def test_rejects_unknown_player_in_events(self):
        with pytest.raises(ValidationError, match="unknown player_name"):
            ReplayInput(
                seed=1.0,
                player_names=PLAYER_NAMES,
                events=(
                    ReplayInputEvent(
                        player_name="UnknownPlayer",
                        action=GameAction.DISCARD,
                    ),
                ),
            )

    def test_accepts_valid_events(self):
        replay = ReplayInput(
            seed=1.0,
            player_names=PLAYER_NAMES,
            events=(
                ReplayInputEvent(
                    player_name="Alice",
                    action=GameAction.DISCARD,
                    data={"tile_id": 0},
                ),
                ReplayInputEvent(
                    player_name="Bob",
                    action=GameAction.DISCARD,
                    data={"tile_id": 1},
                ),
            ),
        )
        assert len(replay.events) == 2

    def test_frozen(self):
        replay = ReplayInput(seed=1.0, player_names=PLAYER_NAMES, events=())
        with pytest.raises(ValidationError):
            replay.seed = 2.0


class TestReplayStep:
    def test_construction_with_state_before_and_after(self):
        state_before = create_game_state()
        state_after = create_game_state(round_number=1)
        input_event = ReplayInputEvent(player_name="Alice", action=GameAction.DISCARD, data={"tile_id": 0})
        discard_data = DiscardEvent(
            seat=0,
            tile_id=0,
            is_tsumogiri=True,
            is_riichi=False,
            target="all",
        )
        service_event = ServiceEvent(event=EventType.DISCARD, data=discard_data)

        step = ReplayStep(
            input_event=input_event,
            emitted_events=(service_event,),
            state_before=state_before,
            state_after=state_after,
        )
        assert step.state_before is state_before
        assert step.state_after is state_after
        assert step.synthetic is False

    def test_synthetic_flag(self):
        state = create_game_state()
        step = ReplayStep(
            input_event=ReplayInputEvent(player_name="Alice", action=GameAction.CONFIRM_ROUND),
            synthetic=True,
            emitted_events=(),
            state_before=state,
            state_after=state,
        )
        assert step.synthetic is True


class TestReplayTrace:
    def test_construction(self):
        state = create_game_state()
        trace = ReplayTrace(
            seed=42.0,
            seat_by_player={"Alice": 0, "Bob": 1, "Charlie": 2, "Diana": 3},
            startup_events=(),
            initial_state=state,
            steps=(),
            final_state=state,
        )
        assert trace.seed == 42.0
        assert trace.seat_by_player["Alice"] == 0
        assert trace.initial_state is state
        assert trace.final_state is state
