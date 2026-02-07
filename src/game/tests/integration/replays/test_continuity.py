"""Replay scenario: state transition chaining invariant.

Verify state_before of step N equals state_after of step N-1,
ensuring the replay trace forms a continuous state chain.
"""

from game.logic.enums import GameAction
from game.messaging.events import EventType
from game.replay.models import ReplayInputEvent
from game.replay.runner import run_replay_async
from game.tests.integration.replays.helpers import (
    PLAYER_NAMES,
    SEED,
    build_replay_from_input_events,
    collect_produced_events,
    find_produced_event,
    probe_current_player,
)


async def test_transition_state_continuity():
    """ReplayStep.state_before of step N equals state_after of step N-1."""
    name, tile = await probe_current_player()
    input_events = [ReplayInputEvent(player_name=name, action=GameAction.DISCARD, data={"tile_id": tile})]
    replay = build_replay_from_input_events(
        seed=SEED,
        player_names=PLAYER_NAMES,
        input_events=input_events,
    )

    trace = await run_replay_async(replay)
    produced_events = collect_produced_events(trace)

    if trace.steps:
        assert trace.steps[0].state_before == trace.initial_state

    for i in range(1, len(trace.steps)):
        assert trace.steps[i].state_before == trace.steps[i - 1].state_after, (
            f"State discontinuity between step {i - 1} and step {i}"
        )

    if trace.steps:
        assert trace.steps[-1].state_after == trace.final_state
    find_produced_event(produced_events, EventType.DISCARD)
