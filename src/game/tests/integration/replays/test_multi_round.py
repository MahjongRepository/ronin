"""Replay scenario: multi-round progression with round advancement and score changes."""

from game.messaging.events import EventType
from game.replay.runner import run_replay_async
from game.tests.integration.replays.helpers import (
    PLAYER_NAMES,
    SEED,
    build_discard_sequence,
    build_replay_from_input_events,
    collect_produced_events,
)


async def test_multi_round_replay():
    """Play through enough actions for multiple rounds with auto_confirm_rounds."""
    input_events = await build_discard_sequence(seed=SEED, count=200)
    replay = build_replay_from_input_events(
        seed=SEED,
        player_names=PLAYER_NAMES,
        input_events=input_events,
    )
    trace = await run_replay_async(replay, strict=False)
    produced_events = collect_produced_events(trace)

    round_end_count = sum(1 for event in produced_events if event.event == EventType.ROUND_END)
    assert round_end_count >= 1

    final_scores = [p.score for p in trace.final_state.round_state.players]
    initial_scores = [p.score for p in trace.initial_state.round_state.players]
    state_changed = (
        trace.final_state.round_number > trace.initial_state.round_number or final_scores != initial_scores
    )
    assert state_changed
