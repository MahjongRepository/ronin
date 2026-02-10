"""Integration test: load a real game replay file and verify event playback."""

from pathlib import Path

from game.logic.enums import GameAction
from game.logic.events import EventType, SeatTarget
from game.replay import run_replay_async
from game.replay.loader import load_replay_from_file

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "simple_cases"


async def test_single_discard_replay_from_file():
    """Load single_discard.txt, play it through the runner, and verify events."""
    replay = load_replay_from_file(FIXTURES_DIR / "single_discard.txt")

    # Verify loaded replay metadata matches the known fixture content
    assert replay.seed == 0.7466046300533131
    # player_names is in reconstructed input order (for fill_seats), not seat order
    assert set(replay.player_names) == {"Ojisan", "Ichihime", "Akagi", "Wanjirou"}
    assert len(replay.events) == 1  # single discard action
    assert replay.events[0].player_name == "Ojisan"

    # Play the replay
    trace = await run_replay_async(replay, auto_pass_calls=True)

    # Verify trace structure
    assert trace.seed == replay.seed
    assert len(trace.seat_by_player) == 4

    # Verify startup events contain GAME_STARTED and ROUND_STARTED
    startup_types = [e.event for e in trace.startup_events]
    assert EventType.GAME_STARTED in startup_types
    assert EventType.ROUND_STARTED in startup_types

    # Startup should include per-seat ROUND_STARTED events (4 seats)
    round_started_seat_events = [
        e
        for e in trace.startup_events
        if e.event == EventType.ROUND_STARTED and isinstance(e.target, SeatTarget)
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


async def test_pon_meld_replay_from_file():
    """Load pon_meld.txt, play it through the runner, and verify pon call."""
    replay = load_replay_from_file(FIXTURES_DIR / "pon_meld.txt")

    assert replay.seed == 0.7466046300533131
    assert set(replay.player_names) == {"Ojisan", "Ichihime", "Akagi", "Wanjirou"}
    # 2 discards before pon + 1 pon + 1 discard after pon = 4 actions
    assert len(replay.events) == 4

    pon_events = [e for e in replay.events if e.action == GameAction.CALL_PON]
    assert len(pon_events) == 1
    assert pon_events[0].player_name == "Wanjirou"
    assert pon_events[0].data["tile_id"] == 129

    # Play the replay
    trace = await run_replay_async(replay, auto_pass_calls=True)

    assert trace.seed == replay.seed
    assert len(trace.seat_by_player) == 4

    # Verify startup events
    startup_types = [e.event for e in trace.startup_events]
    assert EventType.GAME_STARTED in startup_types
    assert EventType.ROUND_STARTED in startup_types

    # Find the pon step among non-synthetic steps
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    assert len(non_synthetic_steps) == 4

    pon_step = non_synthetic_steps[2]
    assert pon_step.input_event.action == GameAction.CALL_PON
    assert pon_step.input_event.player_name == "Wanjirou"

    step_event_types = [e.event for e in pon_step.emitted_events]
    assert EventType.MELD in step_event_types

    # Discard after pon comes from the caller (Wanjirou)
    post_pon_discard = non_synthetic_steps[3]
    assert post_pon_discard.input_event.action == GameAction.DISCARD
    assert post_pon_discard.input_event.player_name == "Wanjirou"

    assert trace.steps[-1].state_after == trace.final_state


async def test_chi_meld_replay_from_file():
    """Load chi_meld.txt, play it through the runner, and verify chi call."""
    replay = load_replay_from_file(FIXTURES_DIR / "chi_meld.txt")

    assert replay.seed == 0.7466046300533131
    assert set(replay.player_names) == {"Ojisan", "Ichihime", "Akagi", "Wanjirou"}

    chi_events = [e for e in replay.events if e.action == GameAction.CALL_CHI]
    assert len(chi_events) == 1
    assert chi_events[0].player_name == "Wanjirou"
    assert chi_events[0].data["tile_id"] == 41
    assert sorted(chi_events[0].data["sequence_tiles"]) == [45, 51]

    # Also contains 2 pon calls earlier in the sequence
    pon_events = [e for e in replay.events if e.action == GameAction.CALL_PON]
    assert len(pon_events) == 2

    # Play the replay
    trace = await run_replay_async(replay, auto_pass_calls=True)

    assert trace.seed == replay.seed
    assert len(trace.seat_by_player) == 4

    # Find the chi step among non-synthetic steps
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    chi_steps = [s for s in non_synthetic_steps if s.input_event.action == GameAction.CALL_CHI]
    assert len(chi_steps) == 1

    chi_step = chi_steps[0]
    assert chi_step.input_event.player_name == "Wanjirou"

    step_event_types = [e.event for e in chi_step.emitted_events]
    assert EventType.MELD in step_event_types

    # Discard after chi: find the step right after the chi
    chi_idx = non_synthetic_steps.index(chi_step)
    post_chi_discard = non_synthetic_steps[chi_idx + 1]
    assert post_chi_discard.input_event.action == GameAction.DISCARD
    assert post_chi_discard.input_event.player_name == "Wanjirou"

    assert trace.steps[-1].state_after == trace.final_state
