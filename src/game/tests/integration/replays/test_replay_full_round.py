"""Integration test: replay full games from fixture files and verify structural correctness."""

from pathlib import Path

from game.logic.enums import GamePhase
from game.logic.events import EventType, GameEndedEvent
from game.logic.rng import RNG_VERSION
from game.replay import run_replay_async
from game.replay.loader import load_replay_from_file

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "full_round"

PLAYERS = {"Akagi", "Wanjirou", "Ichihime", "Ojisan"}
STARTING_SCORE = 25000


async def test_full_game_flow():
    """Replay a complete multi-round game and verify structural correctness.

    Verifies:
    - Replay loads and runs to completion
    - Game ends properly with final standings
    - State transitions are consistent across all steps
    - All required event types appear in the event stream
    - Scores sum to the expected total
    """
    replay = load_replay_from_file(FIXTURES_DIR / "full_game.txt")

    assert isinstance(replay.seed, str)
    assert len(replay.seed) == 192
    assert replay.rng_version == RNG_VERSION
    assert set(replay.player_names) == PLAYERS

    trace = await run_replay_async(replay, auto_pass_calls=True)

    # --- Trace structure ---
    assert trace.seed == replay.seed
    assert trace.rng_version == RNG_VERSION
    assert len(trace.seat_by_player) == 4

    # --- Startup events ---
    startup_types = {e.event for e in trace.startup_events}
    assert EventType.GAME_STARTED in startup_types
    assert EventType.ROUND_STARTED in startup_types
    assert EventType.DRAW in startup_types

    # --- Initial state ---
    initial = trace.initial_state
    assert initial.game_phase == GamePhase.IN_PROGRESS
    assert initial.round_number == 0
    assert initial.round_state.round_wind == 0  # East
    for player in initial.round_state.players:
        assert player.score == STARTING_SCORE
        assert len(player.melds) == 0
        assert len(player.discards) == 0

    # --- Multiple rounds played ---
    round_end_steps = [
        s for s in trace.steps if any(e.event == EventType.ROUND_END for e in s.emitted_events)
    ]
    assert len(round_end_steps) >= 1  # at least one round completed

    # --- Game ended ---
    final = trace.final_state
    assert final.game_phase == GamePhase.FINISHED

    # Game end event was emitted
    game_end_events = [
        e
        for step in trace.steps
        for e in step.emitted_events
        if e.event == EventType.GAME_END and isinstance(e.data, GameEndedEvent)
    ]
    assert len(game_end_events) == 1
    game_result = game_end_events[0].data.result

    # --- Final standings ---
    assert len(game_result.standings) == 4
    raw_scores = {s.name: s.score for s in game_result.standings}
    assert sum(raw_scores.values()) == STARTING_SCORE * 4  # scores conserved

    # Uma-adjusted scores sum to zero
    final_scores = {s.name: s.final_score for s in game_result.standings}
    assert sum(final_scores.values()) == 0

    # Standings are ordered by score (1st to 4th)
    standing_scores = [s.final_score for s in game_result.standings]
    assert standing_scores == sorted(standing_scores, reverse=True)

    # --- State transition consistency ---
    assert trace.steps[0].state_before == trace.initial_state
    assert trace.steps[-1].state_after == trace.final_state

    for i in range(len(trace.steps) - 1):
        assert trace.steps[i].state_after == trace.steps[i + 1].state_before

    # --- Event stream completeness ---
    all_event_types = {e.event for step in trace.steps for e in step.emitted_events}
    assert EventType.DISCARD in all_event_types
    assert EventType.DRAW in all_event_types
    assert EventType.ROUND_END in all_event_types
