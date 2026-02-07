"""Replay scenario: determinism regression across multiple runs."""

from game.logic.enums import GameAction
from game.replay.models import ReplayInputEvent
from game.replay.runner import run_replay_async
from game.tests.integration.replays.helpers import (
    PLAYER_NAMES,
    SEED,
    build_replay_from_input_events,
    collect_produced_events,
    probe_current_player,
)


async def test_determinism_regression():
    """Run same ReplayInput 3 times, assert identical results."""
    name, tile = await probe_current_player()
    input_events = [ReplayInputEvent(player_name=name, action=GameAction.DISCARD, data={"tile_id": tile})]
    replay = build_replay_from_input_events(
        seed=SEED,
        player_names=PLAYER_NAMES,
        input_events=input_events,
    )

    traces = [await run_replay_async(replay) for _ in range(3)]

    for i in range(1, len(traces)):
        assert traces[0].final_state == traces[i].final_state
        assert len(traces[0].steps) == len(traces[i].steps)
        assert traces[0].seat_by_player == traces[i].seat_by_player
        for s0, si in zip(traces[0].steps, traces[i].steps, strict=False):
            assert s0.input_event == si.input_event
            assert [event.model_dump() for event in s0.emitted_events] == [
                event.model_dump() for event in si.emitted_events
            ]
        assert [event.model_dump() for event in collect_produced_events(traces[0])] == [
            event.model_dump() for event in collect_produced_events(traces[i])
        ]
