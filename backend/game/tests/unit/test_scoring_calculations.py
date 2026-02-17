"""
Unit tests for scoring utility functions.

Tests _goshashonyu_round (Japanese rounding), _get_winner_seats, calculate_final_scores,
and finalize_game.
"""

from game.logic.game import _get_winner_seats, _goshashonyu_round, calculate_final_scores, finalize_game
from game.logic.settings import GameSettings
from game.logic.types import (
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    YakuInfo,
)
from game.tests.conftest import create_game_state, create_player, create_round_state


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    """Create stub YakuInfo list for tests where yaku content is not asserted."""
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


class TestGetWinnerSeatsDoubleRon:
    """Test _get_winner_seats extracts seats from double ron results."""

    def test_double_ron_result(self):
        result = DoubleRonResult(
            loser_seat=1,
            winning_tile=42,
            winners=[
                DoubleRonWinner(
                    winner_seat=0,
                    hand_result=HandResultInfo(han=1, fu=30, yaku=_yaku(0)),
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                ),
                DoubleRonWinner(
                    winner_seat=3,
                    hand_result=HandResultInfo(han=2, fu=30, yaku=_yaku(0)),
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                ),
            ],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        assert _get_winner_seats(result) == [0, 3]


class TestGoshashonyuRound:
    """Test _goshashonyu_round: Japanese rounding to nearest N with 0.5 rounding down."""

    def test_positive_remainder_below_500_rounds_down(self):
        # 12300 -> 12.3 -> 12
        assert _goshashonyu_round(12300, 500) == 12

    def test_positive_remainder_exactly_500_rounds_down(self):
        # 12500 -> 12.5 -> 12
        assert _goshashonyu_round(12500, 500) == 12

    def test_positive_remainder_above_500_rounds_up(self):
        # 12600 -> 12.6 -> 13
        assert _goshashonyu_round(12600, 500) == 13

    def test_positive_exact_thousands(self):
        # 12000 -> 12.0 -> 12
        assert _goshashonyu_round(12000, 500) == 12

    def test_negative_remainder_below_500_rounds_toward_zero(self):
        # -1300 -> -1.3 -> -1
        assert _goshashonyu_round(-1300, 500) == -1

    def test_negative_remainder_exactly_500_rounds_toward_zero(self):
        # -1500 -> -1.5 -> -1
        assert _goshashonyu_round(-1500, 500) == -1

    def test_negative_remainder_above_500_rounds_away_from_zero(self):
        # -1900 -> -1.9 -> -2
        assert _goshashonyu_round(-1900, 500) == -2

    def test_negative_remainder_600_rounds_away_from_zero(self):
        # -1600 -> -1.6 -> -2
        assert _goshashonyu_round(-1600, 500) == -2

    def test_negative_exact_thousands(self):
        # -19000 -> -19.0 -> -19
        assert _goshashonyu_round(-19000, 500) == -19

    def test_zero(self):
        assert _goshashonyu_round(0, 500) == 0

    def test_positive_remainder_900(self):
        # 11900 -> 11.9 -> 12
        assert _goshashonyu_round(11900, 500) == 12

    def test_negative_remainder_100(self):
        # -11100 -> -11.1 -> -11
        assert _goshashonyu_round(-11100, 500) == -11


class TestCalculateFinalScores:
    """Test calculate_final_scores: Convert raw points to uma+oka final scores."""

    def test_standard_case(self):
        raw = [(0, 42300), (1, 28100), (2, 18600), (3, 11000)]
        result = calculate_final_scores(raw, GameSettings())

        assert result == [(0, 52), (1, 8), (2, -21), (3, -39)]

    def test_zero_sum_invariant(self):
        raw = [(0, 42300), (1, 28100), (2, 18600), (3, 11000)]
        result = calculate_final_scores(raw, GameSettings())

        total = sum(score for _, score in result)
        assert total == 0

    def test_equal_scores_all_25000(self):
        raw = [(0, 25000), (1, 25000), (2, 25000), (3, 25000)]
        result = calculate_final_scores(raw, GameSettings())

        assert result == [(0, 35), (1, 5), (2, -15), (3, -25)]
        assert sum(score for _, score in result) == 0

    def test_oka_only_applied_to_first_place(self):
        raw = [(0, 30000), (1, 30000), (2, 20000), (3, 20000)]
        result = calculate_final_scores(raw, GameSettings())

        assert result == [(0, 40), (1, 10), (2, -20), (3, -30)]

    def test_negative_raw_score(self):
        raw = [(0, 55000), (1, 25000), (2, 25000), (3, -5000)]
        result = calculate_final_scores(raw, GameSettings())

        assert result == [(0, 65), (1, 5), (2, -15), (3, -55)]
        assert sum(score for _, score in result) == 0

    def test_goshashonyu_rounding_500_down_600_up(self):
        raw = [(0, 30600), (1, 30500), (2, 19500), (3, 19400)]
        result = calculate_final_scores(raw, GameSettings())

        assert result == [(0, 41), (1, 10), (2, -20), (3, -31)]
        assert sum(score for _, score in result) == 0

    def test_zero_sum_adjustment_corrects_first_place(self):
        raw = [(0, 30900), (1, 30900), (2, 19100), (3, 19100)]
        result = calculate_final_scores(raw, GameSettings())

        total = sum(score for _, score in result)
        assert total == 0

    def test_seat_order_preserved_in_output(self):
        raw = [(2, 42300), (0, 28100), (3, 18600), (1, 11000)]
        result = calculate_final_scores(raw, GameSettings())

        assert result[0][0] == 2  # 1st place
        assert result[1][0] == 0  # 2nd place
        assert result[2][0] == 3  # 3rd place
        assert result[3][0] == 1  # 4th place


class TestFinalizeGameRiichiSticks:
    """Test finalize_game awards leftover riichi sticks to the winner."""

    def test_leftover_riichi_awarded_to_winner(self):
        """Leftover riichi sticks are awarded to the highest-scoring player."""
        players = tuple(create_player(seat=i, score=score) for i, score in enumerate([30000, 25000, 22000, 23000]))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state, riichi_sticks=2)  # 2 * 1000 = 2000 bonus

        new_state, result = finalize_game(game_state)

        # seat 0 had highest raw score (30000) and gets the 2000 riichi bonus
        assert new_state.round_state.players[0].score == 32000
        assert new_state.riichi_sticks == 0
        assert result.standings[0].score == 32000
