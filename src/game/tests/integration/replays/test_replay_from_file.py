"""Integration test: load a real game replay file and verify event playback."""

from pathlib import Path

from game.logic.enums import GameAction
from game.logic.events import EventType, SeatTarget
from game.logic.rng import RNG_VERSION
from game.replay import run_replay_async
from game.replay.loader import load_replay_from_file

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "simple_cases"


async def test_single_discard_replay_from_file():
    """Load single_discard.txt, play it through the runner, and verify events."""
    replay = load_replay_from_file(FIXTURES_DIR / "single_discard.txt")

    # Verify loaded replay metadata
    assert isinstance(replay.seed, str)
    assert len(replay.seed) == 192  # 96-byte hex seed
    assert replay.rng_version == RNG_VERSION
    assert set(replay.player_names) == {"Ojisan", "Ichihime", "Akagi", "Wanjirou"}
    assert len(replay.events) == 1  # single discard action
    assert replay.events[0].action == GameAction.DISCARD

    # Play the replay
    trace = await run_replay_async(replay)

    # Verify trace structure
    assert trace.seed == replay.seed
    assert trace.rng_version == RNG_VERSION
    assert len(trace.seat_by_player) == 4

    # Verify startup events contain GAME_STARTED and ROUND_STARTED
    startup_types = [e.event for e in trace.startup_events]
    assert EventType.GAME_STARTED in startup_types
    assert EventType.ROUND_STARTED in startup_types

    # Startup should include per-seat ROUND_STARTED events (4 seats)
    round_started_seat_events = [
        e for e in trace.startup_events if e.event == EventType.ROUND_STARTED and isinstance(e.target, SeatTarget)
    ]
    assert len(round_started_seat_events) == 4

    # Startup should include dealer draw
    draw_events = [e for e in trace.startup_events if e.event == EventType.DRAW]
    assert len(draw_events) >= 1

    # Verify the discard step produced DISCARD event
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    assert len(non_synthetic_steps) == 1

    discard_step = non_synthetic_steps[0]
    step_event_types = [e.event for e in discard_step.emitted_events]
    assert EventType.DISCARD in step_event_types

    # State transitions are consistent: first step starts from initial state
    assert discard_step.state_before == trace.initial_state

    # Last step ends at final state (regardless of synthetic steps)
    assert trace.steps[-1].state_after == trace.final_state
