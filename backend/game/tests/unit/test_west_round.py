from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from game.logic.enums import AbortiveDrawType, GameEndCause, HandLimit
from game.logic.game import _get_wind_for_unique_dealers, game_end_cause, process_round_end
from game.logic.settings import EnchousenType, GameSettings, GameType
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.types import (
    AbortiveDrawResult,
    DoubleRonResult,
    DoubleRonWinner,
    ExhaustiveDrawResult,
    HandResultInfo,
    NagashiManganResult,
    RoundResult,
    TenpaiHand,
    TsumoResult,
    YakuInfo,
)
from game.tests.conftest import create_game_state
from game.tests.helpers.wall import make_wall

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


def _west_game_state(
    *,
    unique_dealers: int = 9,
    player_scores: list[int] | None = None,
    dealer_seat: int = 0,
    winning_score_threshold: int = 30000,
    enchousen: EnchousenType = EnchousenType.SUDDEN_DEATH,
    game_type: GameType = GameType.HANCHAN,
    round_wind: int = 2,
    has_agariyame: bool = True,
) -> MahjongGameState:
    scores = player_scores or [25000, 25000, 25000, 25000]
    players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
    round_state = MahjongRoundState(wall=make_wall(), players=players, dealer_seat=dealer_seat, round_wind=round_wind)

    settings = GameSettings(
        game_type=game_type,
        enchousen=enchousen,
        winning_score_threshold=winning_score_threshold,
        has_agariyame=has_agariyame,
    )
    return create_game_state(
        round_state=round_state,
        unique_dealers=unique_dealers,
        settings=settings,
    )


def _tsumo(winner_seat: int) -> TsumoResult:
    return TsumoResult(
        honba_bonus=0,
        winner_seat=winner_seat,
        hand_result=HandResultInfo(limit=HandLimit.NONE, han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000),
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        riichi_sticks_collected=0,
        closed_tiles=[0, 1, 2, 3],
        melds=[],
        win_tile=3,
    )


def _exhaustive_draw(*, tempai_seats: list[int], noten_seats: list[int]) -> ExhaustiveDrawResult:
    return ExhaustiveDrawResult(
        tempai_seats=tempai_seats,
        noten_seats=noten_seats,
        tenpai_hands=[TenpaiHand(seat=s, closed_tiles=[], melds=[]) for s in tempai_seats],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
    )


# ============================================================================
# End condition: winning_score_threshold (configurable)
# ============================================================================


class TestWestRoundEndCondition:
    def test_west_round_end__when_player_reaches_threshold__should_end_game(self):
        gs = _west_game_state(unique_dealers=9, player_scores=[30000, 25000, 22000, 23000])
        assert (
            game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3)
            == GameEndCause.TARGET_REACHED
        )

    def test_west_round_end__when_no_player_reaches_threshold__should_continue_game(self):
        gs = _west_game_state(unique_dealers=9, player_scores=[29000, 25000, 23000, 23000])
        assert game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3) is None

    def test_west_round_end__when_threshold_reached_mid_west__should_end_game(self):
        gs = _west_game_state(unique_dealers=11, player_scores=[35000, 20000, 22000, 23000])
        assert (
            game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3)
            == GameEndCause.TARGET_REACHED
        )

    def test_west_round_end__when_custom_threshold_not_reached__should_continue_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            player_scores=[35000, 20000, 22000, 23000],
            winning_score_threshold=40000,
        )
        assert game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3) is None

    def test_west_round_end__when_custom_threshold_reached__should_end_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            player_scores=[40000, 15000, 22000, 23000],
            winning_score_threshold=40000,
        )
        assert (
            game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3)
            == GameEndCause.TARGET_REACHED
        )

    def test_west_round_end__when_still_in_primary_wind__should_ignore_threshold(self):
        scores = [35000, 20000, 22000, 23000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(wall=make_wall(), players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.HANCHAN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=7, settings=settings)

        assert game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3) is None


# ============================================================================
# Dealer renchan in West: applies but threshold overrides
# ============================================================================


class TestWestRoundRenchanOverride:
    def test_west_renchan__when_dealer_wins_with_threshold_reached__should_end_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            dealer_seat=0,
            player_scores=[30000, 24000, 23000, 23000],
        )
        # Dealer tsumo → renchan (unique_dealers stays 9)
        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.unique_dealers == 9  # renchan
        assert new_gs.round_state.dealer_seat == 0  # dealer stays
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            == GameEndCause.TARGET_REACHED
        )

    def test_west_renchan__when_dealer_wins_without_threshold__should_continue_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            dealer_seat=0,
            player_scores=[29000, 24000, 24000, 23000],
        )
        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.unique_dealers == 9  # renchan
        assert new_gs.round_state.dealer_seat == 0
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            is None
        )

    def test_west_renchan__when_dealer_tenpai_draw_with_threshold_reached__should_end_game(self):
        gs = _west_game_state(
            unique_dealers=10,
            dealer_seat=1,
            player_scores=[24000, 31000, 22000, 23000],
        )

        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.round_state.dealer_seat == 1  # dealer stays (tenpai renchan)
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            == GameEndCause.TARGET_REACHED
        )

    def test_west_renchan__when_dealer_tenpai_draw_without_threshold__should_continue_game(self):
        gs = _west_game_state(
            unique_dealers=10,
            dealer_seat=1,
            player_scores=[29000, 24000, 24000, 23000],
        )

        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.round_state.dealer_seat == 1  # renchan
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            is None
        )


def _end_cause_after(gs: MahjongGameState, result: RoundResult) -> GameEndCause | None:
    finished = gs.model_copy(update={"round_state": gs.round_state.model_copy(update={"result": result})})
    return game_end_cause(
        process_round_end(finished, result),
        ended_round_wind=gs.round_state.round_wind,
        ended_dealer_seat=gs.round_state.dealer_seat,
    )


def _double_ron(*winner_seats: int, loser_seat: int) -> DoubleRonResult:
    return DoubleRonResult(
        loser_seat=loser_seat,
        winning_tile=0,
        winners=[
            DoubleRonWinner(
                honba_bonus=0,
                winner_seat=seat,
                hand_result=HandResultInfo(
                    limit=HandLimit.NONE, han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000
                ),
                score_changes={},
                riichi_sticks_collected=0,
                closed_tiles=[0],
                melds=[],
            )
            for seat in winner_seats
        ],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
    )


class TestDealerStop:
    @pytest.mark.parametrize(
        ("unique_dealers", "round_wind", "dealer_seat", "scores", "expected"),
        [
            pytest.param(
                8, 1, 3, [24000, 23000, 23000, 30000], GameEndCause.LENGTH, id="south_4_first_at_exact_target"
            ),
            pytest.param(8, 1, 3, [24000, 23000, 23000, 29900], None, id="south_4_first_just_below_target"),
            pytest.param(8, 1, 3, [24000, 32000, 23000, 31000], None, id="south_4_second_above_target"),
            pytest.param(8, 1, 3, [30000, 23000, 23000, 30000], None, id="south_4_tie_lost_to_earlier_seat"),
            pytest.param(
                9, 2, 0, [30000, 30000, 20000, 20000], GameEndCause.TARGET_REACHED, id="west_1_tie_won_over_later_seat"
            ),
            pytest.param(12, 2, 3, [31000, 23000, 23000, 23000], None, id="west_4_only_non_dealer_at_target"),
        ],
    )
    def test_game_end_cause__when_dealer_wins_from_all_last_on__should_stop_only_first_at_target(
        self, unique_dealers, round_wind, dealer_seat, scores, expected
    ):
        gs = _west_game_state(
            unique_dealers=unique_dealers, round_wind=round_wind, dealer_seat=dealer_seat, player_scores=scores
        )

        assert _end_cause_after(gs, _tsumo(winner_seat=dealer_seat)) == expected

    @pytest.mark.parametrize(
        "result",
        [
            pytest.param(_exhaustive_draw(tempai_seats=[3], noten_seats=[0, 1, 2]), id="exhaustive_draw"),
            pytest.param(
                NagashiManganResult(
                    rivers=[],
                    qualifying_seats=[1],
                    tempai_seats=[3],
                    noten_seats=[0, 1, 2],
                    tenpai_hands=[TenpaiHand(seat=3, closed_tiles=[], melds=[])],
                    scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
                    score_changes={0: 0, 1: 0, 2: 0, 3: 0},
                ),
                id="nagashi_mangan",
            ),
        ],
    )
    def test_game_end_cause__when_south_4_dealer_tenpai_and_first_at_target__should_stop(self, result):
        gs = _west_game_state(unique_dealers=8, round_wind=1, dealer_seat=3, player_scores=[24000, 23000, 23000, 30000])

        assert _end_cause_after(gs, result) == GameEndCause.LENGTH

    def test_game_end_cause__when_east_4_dealer_wins_first_at_target__should_stop(self):
        gs = _west_game_state(
            unique_dealers=4,
            round_wind=0,
            dealer_seat=3,
            player_scores=[24000, 23000, 23000, 30000],
            game_type=GameType.TONPUSEN,
        )

        assert _end_cause_after(gs, _tsumo(winner_seat=3)) == GameEndCause.LENGTH

    def test_game_end_cause__when_south_3_winner_becomes_first_placed_dealer__should_play_south_4(self):
        gs = _west_game_state(unique_dealers=7, round_wind=1, dealer_seat=2, player_scores=[23000, 23000, 23000, 31000])

        assert _end_cause_after(gs, _tsumo(winner_seat=3)) is None

    def test_game_end_cause__when_double_ron_lifts_only_the_non_dealer_to_target__should_repeat(self):
        gs = _west_game_state(unique_dealers=9, dealer_seat=0, player_scores=[28000, 32000, 20000, 20000])

        assert _end_cause_after(gs, _double_ron(0, 1, loser_seat=2)) is None

    def test_game_end_cause__when_abortive_draw_in_west_4_with_dealer_first_at_target__should_repeat(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[23000, 23000, 23000, 31000])
        result = AbortiveDrawResult(
            reason=AbortiveDrawType.FOUR_WINDS,
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        assert _end_cause_after(gs, result) is None

    def test_game_end_cause__when_no_extension_and_dealer_first_below_target__should_stop(self):
        gs = _west_game_state(
            unique_dealers=8,
            round_wind=1,
            dealer_seat=3,
            player_scores=[24000, 23000, 23000, 28000],
            enchousen=EnchousenType.NONE,
        )

        assert _end_cause_after(gs, _tsumo(winner_seat=3)) == GameEndCause.LENGTH

    @pytest.mark.parametrize(
        ("unique_dealers", "round_wind", "dealer_seat", "scores", "expected"),
        [
            pytest.param(8, 1, 3, [24000, 23000, 23000, 31000], None, id="south_4_dealer_first_keeps_playing"),
            pytest.param(
                10, 2, 1, [31000, 24000, 22000, 23000], GameEndCause.TARGET_REACHED, id="west_non_dealer_target_ends"
            ),
        ],
    )
    def test_game_end_cause__when_agariyame_off__should_keep_the_threshold_over_a_repeat(
        self, unique_dealers, round_wind, dealer_seat, scores, expected
    ):
        gs = _west_game_state(
            unique_dealers=unique_dealers,
            round_wind=round_wind,
            dealer_seat=dealer_seat,
            player_scores=scores,
            has_agariyame=False,
        )

        assert _end_cause_after(gs, _tsumo(winner_seat=dealer_seat)) == expected


# ============================================================================
# Rotation through West-1...West-4
# ============================================================================


class TestWestRoundRotation:
    def test_west_rotation__when_unique_dealers_9_to_12__should_use_west_wind(self):
        for ud in range(9, 13):
            assert _get_wind_for_unique_dealers(ud) == 2

    def test_west_rotation__when_non_dealer_wins_west_1__should_advance_to_west_2(self):
        gs = _west_game_state(unique_dealers=9, dealer_seat=0, player_scores=[25000, 25000, 25000, 25000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.unique_dealers == 10
        assert new_gs.round_state.dealer_seat == 1
        assert new_gs.round_state.round_wind == 2  # still West

    def test_west_rotation__when_non_dealer_wins_west_4__should_end_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[25000, 25000, 25000, 25000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.unique_dealers == 13
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            == GameEndCause.EXTENSION_LIMIT
        )

    def test_west_rotation__when_dealer_noten_draw_in_west_4__should_end_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[25000, 25000, 25000, 25000])

        result = _exhaustive_draw(tempai_seats=[0], noten_seats=[1, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.unique_dealers == 13
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            == GameEndCause.EXTENSION_LIMIT
        )

    def test_west_rotation__when_dealer_wins_west_4_without_threshold__should_continue_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[29000, 24000, 24000, 23000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=3))
        assert new_gs.unique_dealers == 12  # renchan, not incremented
        assert new_gs.round_state.dealer_seat == 3
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            is None
        )

    def test_west_rotation__when_dealer_wins_west_4_with_threshold__should_end_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[23000, 23000, 24000, 30000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=3))
        assert new_gs.unique_dealers == 12  # renchan
        assert (
            game_end_cause(
                new_gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=gs.round_state.dealer_seat
            )
            == GameEndCause.TARGET_REACHED
        )


# ============================================================================
# Tonpusen sudden death: South round is the extension
# ============================================================================


class TestTonpusenSuddenDeath:
    def test_tonpusen_sudden_death__when_south_without_threshold__should_continue_game(self):
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(wall=make_wall(), players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=6, settings=settings)

        assert game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3) is None

    def test_tonpusen_sudden_death__when_south_with_threshold__should_end_game(self):
        scores = [31000, 24000, 22000, 23000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(wall=make_wall(), players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=6, settings=settings)

        assert (
            game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3)
            == GameEndCause.TARGET_REACHED
        )

    def test_tonpusen_sudden_death__when_past_south_4__should_end_game(self):
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(wall=make_wall(), players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=9, settings=settings)

        assert (
            game_end_cause(gs, ended_round_wind=gs.round_state.round_wind, ended_dealer_seat=3)
            == GameEndCause.EXTENSION_LIMIT
        )
