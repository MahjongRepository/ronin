"""Replay scenario: determinism regression across multiple runs."""

from game.logic.enums import GameAction
from game.logic.events import EventType, SeatTarget
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


async def test_seat_target_events_present_in_emitted_stream():
    """Replay trace includes seat-target draw and round_started events in startup events."""
    name, tile = await probe_current_player()
    input_events = [ReplayInputEvent(player_name=name, action=GameAction.DISCARD, data={"tile_id": tile})]
    replay = build_replay_from_input_events(
        seed=SEED,
        player_names=PLAYER_NAMES,
        input_events=input_events,
    )

    trace = await run_replay_async(replay)

    all_events = list(trace.startup_events) + list(collect_produced_events(trace))

    # round_started with SeatTarget should be in startup events (4 per round start)
    round_started_seat = [
        e for e in all_events if e.event == EventType.ROUND_STARTED and isinstance(e.target, SeatTarget)
    ]
    assert len(round_started_seat) >= 4

    # draw with SeatTarget should appear (dealer draws at game start)
    draw_seat = [e for e in all_events if e.event == EventType.DRAW and isinstance(e.target, SeatTarget)]
    assert len(draw_seat) >= 1


async def test_seat_target_events_deterministic_across_runs():
    """Seat-target events are deterministic: same content across repeated runs."""
    name, tile = await probe_current_player()
    input_events = [ReplayInputEvent(player_name=name, action=GameAction.DISCARD, data={"tile_id": tile})]
    replay = build_replay_from_input_events(
        seed=SEED,
        player_names=PLAYER_NAMES,
        input_events=input_events,
    )

    traces = [await run_replay_async(replay) for _ in range(2)]

    for trace_idx in range(2):
        all_events = list(traces[trace_idx].startup_events) + list(collect_produced_events(traces[trace_idx]))
        seat_events = [e for e in all_events if isinstance(e.target, SeatTarget)]
        assert len(seat_events) > 0

    # Compare seat-target events across both runs
    all_events_0 = list(traces[0].startup_events) + list(collect_produced_events(traces[0]))
    all_events_1 = list(traces[1].startup_events) + list(collect_produced_events(traces[1]))
    seat_0 = [e.data.model_dump() for e in all_events_0 if isinstance(e.target, SeatTarget)]
    seat_1 = [e.data.model_dump() for e in all_events_1 if isinstance(e.target, SeatTarget)]
    assert seat_0 == seat_1
