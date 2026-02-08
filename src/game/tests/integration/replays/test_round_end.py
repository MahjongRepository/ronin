"""Replay scenario: round-end through exhaustive draw after repeated discards."""

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.replay.runner import run_replay_async
from game.tests.integration.replays.helpers import (
    PLAYER_NAMES,
    SEED,
    build_discard_sequence,
    build_replay_from_input_events,
    collect_produced_events,
    find_produced_event,
)


async def test_round_end_replay():
    """Play enough discards to reach round end, verify ROUND_END event and synthetic confirms."""
    input_events = await build_discard_sequence(seed=SEED, count=150)
    replay = build_replay_from_input_events(
        seed=SEED,
        player_names=PLAYER_NAMES,
        input_events=input_events,
    )
    trace = await run_replay_async(replay, strict=False)
    produced_events = collect_produced_events(trace)

    find_produced_event(produced_events, EventType.ROUND_END)

    synthetic_steps = [s for s in trace.steps if s.synthetic]
    if trace.final_state.round_number > 0:
        assert len(synthetic_steps) >= 1
        for s in synthetic_steps:
            assert s.input_event.action == GameAction.CONFIRM_ROUND
