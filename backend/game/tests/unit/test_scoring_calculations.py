from game.logic.game import _goshashonyu_round, calculate_final_scores, finalize_game
from game.logic.settings import GameSettings, LeftoverRiichiBets
from game.logic.state_utils import get_winner_seats
from game.logic.types import (
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    YakuInfo,
)
from game.tests.conftest import create_game_state, create_player, create_round_state


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


class TestGetWinnerSeatsDoubleRon:
    def test_get_winner_seats__when_double_ron__should_return_both_winner_seats(self):
        result = DoubleRonResult(
            loser_seat=1,
            winning_tile=42,
            winners=[
                DoubleRonWinner(
                    winner_seat=0,
                    hand_result=HandResultInfo(han=1, fu=30, yaku=_yaku(0), points=1000),
                    score_changes={0: 0, 1: 0, 2: 0, 3: 0},
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                ),
                DoubleRonWinner(
                    winner_seat=3,
                    hand_result=HandResultInfo(han=2, fu=30, yaku=_yaku(0), points=2000),
                    score_changes={0: 0, 1: 0, 2: 0, 3: 0},
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                ),
            ],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        assert get_winner_seats(result) == (0, 3)


class TestGoshashonyuRound:
    def test_goshashonyu_round__when_positive_remainder_below_500__should_round_down(self):
        # 12300 -> 12.3 -> 12
        assert _goshashonyu_round(12300, 500) == 12

    def test_goshashonyu_round__when_positive_remainder_exactly_500__should_round_down(self):
        # 12500 -> 12.5 -> 12
        assert _goshashonyu_round(12500, 500) == 12

    def test_goshashonyu_round__when_positive_remainder_above_500__should_round_up(self):
        # 12600 -> 12.6 -> 13
        assert _goshashonyu_round(12600, 500) == 13

    def test_goshashonyu_round__when_positive_exact_thousands__should_keep_value(self):
        # 12000 -> 12.0 -> 12
        assert _goshashonyu_round(12000, 500) == 12

    def test_goshashonyu_round__when_negative_remainder_below_500__should_round_toward_zero(self):
        # -1300 -> -1.3 -> -1
        assert _goshashonyu_round(-1300, 500) == -1

    def test_goshashonyu_round__when_negative_remainder_exactly_500__should_round_toward_zero(self):
        # -1500 -> -1.5 -> -1
        assert _goshashonyu_round(-1500, 500) == -1

    def test_goshashonyu_round__when_negative_remainder_above_500__should_round_away_from_zero(self):
        # -1900 -> -1.9 -> -2
        assert _goshashonyu_round(-1900, 500) == -2

    def test_goshashonyu_round__when_negative_exact_thousands__should_keep_value(self):
        # -19000 -> -19.0 -> -19
        assert _goshashonyu_round(-19000, 500) == -19

    def test_goshashonyu_round__when_zero__should_return_zero(self):
        assert _goshashonyu_round(0, 500) == 0


class TestCalculateFinalScores:
    def test_calculate_final_scores__when_distinct_scores__should_apply_uma_oka_and_sum_to_zero(self):
        raw = [(0, 42300), (1, 28100), (2, 18600), (3, 11000)]
        result = calculate_final_scores(raw, GameSettings())
        assert result == [(0, 52), (1, 8), (2, -21), (3, -39)]
        assert sum(score for _, score in result) == 0

    def test_calculate_final_scores__when_all_scores_25000__should_rank_by_seat_order(self):
        raw = [(0, 25000), (1, 25000), (2, 25000), (3, 25000)]
        result = calculate_final_scores(raw, GameSettings())
        assert result == [(0, 35), (1, 5), (2, -15), (3, -25)]
        assert sum(score for _, score in result) == 0

    def test_calculate_final_scores__when_scores_tied__should_give_oka_to_first_place_only(self):
        raw = [(0, 30000), (1, 30000), (2, 20000), (3, 20000)]
        result = calculate_final_scores(raw, GameSettings())
        assert result == [(0, 40), (1, 10), (2, -20), (3, -30)]

    def test_calculate_final_scores__when_raw_score_negative__should_sum_to_zero(self):
        raw = [(0, 55000), (1, 25000), (2, 25000), (3, -5000)]
        result = calculate_final_scores(raw, GameSettings())
        assert result == [(0, 65), (1, 5), (2, -15), (3, -55)]
        assert sum(score for _, score in result) == 0

    def test_calculate_final_scores__when_remainders_500_and_600__should_round_500_down_and_600_up(self):
        raw = [(0, 30600), (1, 30500), (2, 19500), (3, 19400)]
        result = calculate_final_scores(raw, GameSettings())
        assert result == [(0, 41), (1, 10), (2, -20), (3, -31)]
        assert sum(score for _, score in result) == 0

    def test_calculate_final_scores__when_seats_out_of_order__should_list_by_placement(self):
        raw = [(2, 42300), (0, 28100), (3, 18600), (1, 11000)]
        result = calculate_final_scores(raw, GameSettings())
        assert result[0][0] == 2  # 1st place
        assert result[1][0] == 0  # 2nd place
        assert result[2][0] == 3  # 3rd place
        assert result[3][0] == 1  # 4th place


class TestFinalizeGameRiichiSticks:
    def test_finalize_game__when_riichi_sticks_left__should_award_them_to_top_player(self):
        players = tuple(create_player(seat=i, score=score) for i, score in enumerate([30000, 25000, 22000, 23000]))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state, riichi_sticks=2)  # 2 * 1000 = 2000 bonus

        new_state, result = finalize_game(game_state)
        # seat 0 had highest raw score (30000) and gets the 2000 riichi bonus
        assert new_state.round_state.players[0].score == 32000
        assert new_state.riichi_sticks == 0
        assert result.standings[0].score == 32000
        assert result.leftover_riichi_bonus == 2000

    def test_finalize_game__when_leftover_riichi_bets_lost__should_clear_the_sticks_without_a_bonus(self):
        players = tuple(create_player(seat=i, score=score) for i, score in enumerate([30000, 25000, 22000, 21000]))
        round_state = create_round_state(players=players)
        settings = GameSettings(leftover_riichi_bets=LeftoverRiichiBets.LOST)
        game_state = create_game_state(round_state, riichi_sticks=2, settings=settings)

        new_state, result = finalize_game(game_state)

        assert new_state.riichi_sticks == 0
        assert result.standings[0].score == 30000
        assert result.leftover_riichi_bonus == 0
