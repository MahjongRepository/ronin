import json
from pathlib import Path

import pytest

from game.logic.enums import GameAction
from game.logic.events import EventType, RoundEndEvent, SeatTarget
from game.logic.rng import RNG_VERSION
from game.messaging.event_payload import game_event_payload
from game.replay import run_replay
from game.replay.external.tenhou import TenhouConverter
from game.replay.loader import load_replay_from_file
from game.wire.enums import WireEventType

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "simple_cases"
ALL_FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*/*.txt"))


def test_replay_runner__when_single_discard_replay_loaded__should_produce_consistent_trace():
    replay = load_replay_from_file(FIXTURES_DIR / "single_discard.txt")
    # Verify loaded replay metadata
    assert isinstance(replay.seed, str)
    assert len(replay.seed) == 192  # 96-byte hex seed
    assert replay.rng_version == RNG_VERSION
    assert set(replay.player_names) == {"Ojisan", "Ichihime", "Akagi", "Wanjirou"}
    assert len(replay.events) == 1  # single discard action
    assert replay.events[0].action == GameAction.DISCARD

    # Play the replay
    trace = run_replay(replay)
    # Verify trace structure
    assert trace.seed == replay.seed
    assert trace.rng_version == RNG_VERSION
    assert len(trace.seat_by_player) == 4
    # Verify startup events contain GAME_STARTED and ROUND_STARTED
    startup_types = [e.type for e in trace.startup_events]
    assert EventType.GAME_STARTED in startup_types
    assert EventType.ROUND_STARTED in startup_types
    # Startup should include per-seat ROUND_STARTED events (4 seats)
    round_started_seat_events = [
        e for e in trace.startup_events if e.type == EventType.ROUND_STARTED and isinstance(e.target, SeatTarget)
    ]
    assert len(round_started_seat_events) == 4
    # Startup should include dealer draw
    draw_events = [e for e in trace.startup_events if e.type == EventType.DRAW]
    assert len(draw_events) == 1
    # Verify the discard step produced DISCARD event
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    assert len(non_synthetic_steps) == 1
    discard_step = non_synthetic_steps[0]
    step_event_types = [e.type for e in discard_step.emitted_events]
    assert EventType.DISCARD in step_event_types
    # State transitions are consistent: first step starts from initial state
    assert discard_step.state_before == trace.initial_state
    # Last step ends at final state (regardless of synthetic steps)
    assert trace.steps[-1].state_after == trace.final_state


@pytest.mark.parametrize("fixture", ALL_FIXTURES, ids=lambda path: path.stem)
def test_replay_fixture__when_loaded_replayed_and_exported__should_reproduce_its_round_ends_and_rounds(fixture):
    recorded_lines = [json.loads(line) for line in fixture.read_text().splitlines()[1:]]

    trace = run_replay(load_replay_from_file(fixture))
    replayed_round_ends = [
        json.loads(json.dumps(game_event_payload(e))) for e in trace.events if isinstance(e, RoundEndEvent)
    ]
    assert replayed_round_ends == [line for line in recorded_lines if line["t"] == WireEventType.ROUND_END]

    tenhou_xml = TenhouConverter(recorded_lines).convert()
    assert tenhou_xml.count("<INIT ") == sum(line["t"] == WireEventType.ROUND_STARTED for line in recorded_lines)
