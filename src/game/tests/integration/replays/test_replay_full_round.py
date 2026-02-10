"""Integration test: replay full rounds and complete games from real game data."""

from pathlib import Path

from game.logic.enums import GameAction, GamePhase, RoundPhase, RoundResultType
from game.logic.events import EventType, GameEndedEvent, extract_round_result
from game.logic.types import RonResult
from game.replay import run_replay_async
from game.replay.loader import load_replay_from_file

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "full_round"

PLAYERS = {"Akagi", "Wanjirou", "Ichihime", "Ojisan"}
SEED = 0.545359349479906
STARTING_SCORE = 25000


async def test_ron_with_melds_full_round():
    """Replay a full round ending in ron with chi and pon melds.

    Game 324c09e6: East 1, Ichihime (seat 2) wins by ron against Ojisan (seat 3)
    with Yakuhai (haku) + Honitsu (3 han, 30 fu, 3900 points).
    Ichihime has 1 chi meld; Wanjirou (seat 1) has 2 pon melds.
    """
    replay = load_replay_from_file(FIXTURES_DIR / "ron_with_melds.txt")

    assert replay.seed == SEED
    assert set(replay.player_names) == PLAYERS

    # Verify action composition: discards + melds + ron
    discard_count = sum(1 for e in replay.events if e.action == GameAction.DISCARD)
    pon_count = sum(1 for e in replay.events if e.action == GameAction.CALL_PON)
    chi_count = sum(1 for e in replay.events if e.action == GameAction.CALL_CHI)
    ron_count = sum(1 for e in replay.events if e.action == GameAction.CALL_RON)
    assert pon_count == 2
    assert chi_count == 1
    assert ron_count == 1
    assert discard_count > 0

    trace = await run_replay_async(replay, auto_pass_calls=True)

    # --- Trace structure ---
    assert trace.seed == SEED
    assert len(trace.seat_by_player) == 4
    assert trace.seat_by_player["Ichihime"] == 2
    assert trace.seat_by_player["Ojisan"] == 3

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
    assert initial.round_state.dealer_seat == 0
    for player in initial.round_state.players:
        assert player.score == STARTING_SCORE
        assert len(player.melds) == 0
        assert len(player.discards) == 0

    # --- Ron step and round result ---
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]

    # Last non-synthetic step is the ron call
    ron_step = non_synthetic_steps[-1]
    assert ron_step.input_event.action == GameAction.CALL_RON
    assert ron_step.input_event.player_name == "Ichihime"

    round_result = extract_round_result(list(ron_step.emitted_events))
    assert round_result is not None
    assert isinstance(round_result, RonResult)
    assert round_result.type == RoundResultType.RON

    # --- Ron result details ---
    assert round_result.winner_seat == 2  # Ichihime
    assert round_result.loser_seat == 3  # Ojisan
    assert round_result.winning_tile == 41
    assert round_result.hand_result.han == 3
    assert round_result.hand_result.fu == 30
    assert round_result.hand_result.cost_main == 3900
    assert "Yakuhai (haku)" in round_result.hand_result.yaku
    assert "Honitsu" in round_result.hand_result.yaku

    # Score changes: Ichihime +3900, Ojisan -3900, others unchanged
    assert round_result.score_changes == {0: 0, 1: 0, 2: 3900, 3: -3900}
    assert round_result.riichi_sticks_collected == 0

    # --- State right after ron (before round advance) ---
    ended_state = ron_step.state_after
    assert ended_state.round_state.phase == RoundPhase.FINISHED
    assert ended_state.game_phase == GamePhase.IN_PROGRESS

    # Scores on the ended round reflect the ron result
    ended_scores = {p.seat: p.score for p in ended_state.round_state.players}
    assert ended_scores[0] == STARTING_SCORE  # Akagi: unchanged
    assert ended_scores[1] == STARTING_SCORE  # Wanjirou: unchanged
    assert ended_scores[2] == STARTING_SCORE + 3900  # Ichihime: winner
    assert ended_scores[3] == STARTING_SCORE - 3900  # Ojisan: dealt in

    # Meld verification on the ended round state
    ichihime = ended_state.round_state.players[2]
    assert len(ichihime.melds) == 1
    assert ichihime.melds[0].meld_type == "chi"

    wanjirou = ended_state.round_state.players[1]
    assert len(wanjirou.melds) == 2
    assert all(m.meld_type == "pon" for m in wanjirou.melds)

    # Players who called open melds are tracked
    assert 1 in ended_state.round_state.players_with_open_hands  # Wanjirou
    assert 2 in ended_state.round_state.players_with_open_hands  # Ichihime

    # Every player discarded at least once during the round
    for player in ended_state.round_state.players:
        assert len(player.discards) > 0

    # --- Final state (after auto-confirm, next round started) ---
    final = trace.final_state
    assert final.game_phase == GamePhase.IN_PROGRESS
    # Non-dealer won, so dealer rotates and round number advances
    assert final.round_number == 1
    assert final.round_state.round_wind == 0  # Still East wind
    assert final.round_state.dealer_seat == 1  # Dealer rotated to seat 1
    assert final.round_state.phase == RoundPhase.PLAYING

    # Scores carry over to the new round
    final_scores = {p.seat: p.score for p in final.round_state.players}
    assert final_scores[0] == STARTING_SCORE
    assert final_scores[1] == STARTING_SCORE
    assert final_scores[2] == STARTING_SCORE + 3900
    assert final_scores[3] == STARTING_SCORE - 3900

    # New round has clean melds and discards
    for player in final.round_state.players:
        assert len(player.melds) == 0
        assert len(player.discards) == 0

    # --- State transition consistency ---
    assert trace.steps[0].state_before == trace.initial_state
    assert trace.steps[-1].state_after == trace.final_state

    for i in range(len(trace.steps) - 1):
        assert trace.steps[i].state_after == trace.steps[i + 1].state_before

    # --- Event stream completeness ---
    all_event_types = {e.event for step in trace.steps for e in step.emitted_events}
    assert EventType.DISCARD in all_event_types
    assert EventType.MELD in all_event_types
    assert EventType.DRAW in all_event_types
    assert EventType.ROUND_END in all_event_types


async def test_full_game_flow():
    """Replay a complete 13-round game and verify final outcome.

    Game 0316344c: 4 players, 13 rounds, ends with Wanjirou winning.
    Final standings: Wanjirou 36400 (1st), Ichihime 22500 (2nd),
    Ojisan 22400 (3rd), Akagi 18700 (4th).
    """
    replay = load_replay_from_file(FIXTURES_DIR / "full_game.txt")

    assert replay.seed == 0.7140525888333568
    assert set(replay.player_names) == PLAYERS

    trace = await run_replay_async(replay, auto_pass_calls=True)

    # --- 13 rounds played ---
    round_end_steps = [
        s for s in trace.steps if any(e.event == EventType.ROUND_END for e in s.emitted_events)
    ]
    assert len(round_end_steps) == 13

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

    # --- Winner ---
    assert game_result.winner_seat == 1  # Wanjirou
    assert len(game_result.standings) == 4

    # --- Final raw scores (sum must be 100000) ---
    raw_scores = {s.name: s.score for s in game_result.standings}
    assert raw_scores == {
        "Wanjirou": 36400,
        "Ichihime": 22500,
        "Akagi": 18700,
        "Ojisan": 22400,
    }
    assert sum(raw_scores.values()) == 100000

    # --- Uma-adjusted final scores ---
    final_scores = {s.name: s.final_score for s in game_result.standings}
    assert final_scores == {
        "Wanjirou": 46,
        "Ichihime": 3,
        "Akagi": -31,
        "Ojisan": -18,
    }
    assert sum(final_scores.values()) == 0

    # --- Standings are ordered by score (1st to 4th) ---
    standing_scores = [s.final_score for s in game_result.standings]
    assert standing_scores == sorted(standing_scores, reverse=True)

    # --- State transition consistency ---
    assert trace.steps[0].state_before == trace.initial_state
    assert trace.steps[-1].state_after == trace.final_state
