"""
Unit tests for game initialization and progression.
"""

from unittest.mock import MagicMock

from game.logic.enums import AbortiveDrawType, BotType, RoundResultType
from game.logic.game import (
    _goshashonyu_round,
    _process_draw_result,
    calculate_final_scores,
    check_game_end,
    finalize_game,
    init_game,
    process_round_end,
)
from game.logic.state import (
    GamePhase,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    RoundPhase,
)
from game.logic.types import (
    AbortiveDrawResult,
    DoubleRonResult,
    DoubleRonWinner,
    ExhaustiveDrawResult,
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    SeatConfig,
    TsumoResult,
)


def _default_seat_configs() -> list[SeatConfig]:
    """Create standard seat configs for testing: 1 human + 3 bots."""
    return [
        SeatConfig(name="Human"),
        SeatConfig(name="Tsumogiri 1", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", bot_type=BotType.TSUMOGIRI),
    ]


class TestInitGame:
    def test_init_game_creates_four_players(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert len(game_state.round_state.players) == 4

    def test_init_game_first_player_is_human(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.round_state.players[0].name == "Human"

    def test_init_game_starting_scores(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        for player in game_state.round_state.players:
            assert player.score == 25000

    def test_init_game_dealer_is_seat_0(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.round_state.dealer_seat == 0

    def test_init_game_round_wind_is_east(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.round_state.round_wind == 0

    def test_init_game_honba_is_zero(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.honba_sticks == 0

    def test_init_game_riichi_sticks_is_zero(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.riichi_sticks == 0

    def test_init_game_round_number_is_zero(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.round_number == 0

    def test_init_game_unique_dealers_is_one(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.unique_dealers == 1

    def test_init_game_phase_is_in_progress(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.game_phase == GamePhase.IN_PROGRESS

    def test_init_game_round_is_initialized(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        # round should be initialized with dealt tiles
        for player in game_state.round_state.players:
            assert len(player.tiles) == 13
        assert game_state.round_state.phase == RoundPhase.PLAYING

    def test_init_game_uses_seed(self):
        configs = _default_seat_configs()
        game_state1 = init_game(configs, seed=12345.0)
        game_state2 = init_game(configs, seed=12345.0)

        # same seed should produce same hands
        for i in range(4):
            assert game_state1.round_state.players[i].tiles == game_state2.round_state.players[i].tiles

    def test_init_game_different_seed_different_hands(self):
        configs = _default_seat_configs()
        game_state1 = init_game(configs, seed=12345.0)
        game_state2 = init_game(configs, seed=67890.0)

        # different seeds should produce different hands
        assert game_state1.round_state.players[0].tiles != game_state2.round_state.players[0].tiles


class TestProcessRoundEnd:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="Bot1", score=25000),
            MahjongPlayer(seat=2, name="Bot2", score=25000),
            MahjongPlayer(seat=3, name="Bot3", score=25000),
        ]
        round_state = MahjongRoundState(players=players, dealer_seat=0, round_wind=0)
        return MahjongGameState(
            round_state=round_state,
            round_number=0,
            unique_dealers=1,
            honba_sticks=0,
            riichi_sticks=0,
        )

    def _tsumo(self, winner_seat: int) -> TsumoResult:
        return TsumoResult(
            winner_seat=winner_seat,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["Riichi"]),
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
            riichi_sticks_collected=0,
        )

    def _ron(self, winner_seat: int, loser_seat: int) -> RonResult:
        return RonResult(
            winner_seat=winner_seat,
            loser_seat=loser_seat,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["Riichi"]),
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
            riichi_sticks_collected=0,
        )

    def test_abortive_draw_increments_honba(self):
        game_state = self._create_game_state()
        result = AbortiveDrawResult(reason=AbortiveDrawType.FOUR_WINDS)

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 1

    def test_abortive_draw_does_not_rotate_dealer(self):
        game_state = self._create_game_state()
        result = AbortiveDrawResult(reason=AbortiveDrawType.FOUR_WINDS)

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 0
        assert game_state.unique_dealers == 1

    def test_exhaustive_draw_dealer_tempai_increments_honba(self):
        game_state = self._create_game_state()
        result = ExhaustiveDrawResult(
            tempai_seats=[0, 2], noten_seats=[1, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 1

    def test_exhaustive_draw_dealer_tempai_does_not_rotate(self):
        game_state = self._create_game_state()
        result = ExhaustiveDrawResult(
            tempai_seats=[0], noten_seats=[1, 2, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 0
        assert game_state.unique_dealers == 1

    def test_exhaustive_draw_dealer_noten_increments_honba(self):
        game_state = self._create_game_state()
        result = ExhaustiveDrawResult(
            tempai_seats=[1, 2], noten_seats=[0, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 1

    def test_exhaustive_draw_dealer_noten_rotates_dealer(self):
        game_state = self._create_game_state()
        result = ExhaustiveDrawResult(
            tempai_seats=[1], noten_seats=[0, 2, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 1
        assert game_state.unique_dealers == 2

    def test_tsumo_dealer_wins_increments_honba(self):
        game_state = self._create_game_state()
        result = self._tsumo(winner_seat=0)

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 1

    def test_tsumo_dealer_wins_does_not_rotate(self):
        game_state = self._create_game_state()
        result = self._tsumo(winner_seat=0)

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 0
        assert game_state.unique_dealers == 1

    def test_tsumo_dealer_loses_resets_honba(self):
        game_state = self._create_game_state()
        game_state.honba_sticks = 3
        result = self._tsumo(winner_seat=2)

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 0

    def test_tsumo_dealer_loses_rotates_dealer(self):
        game_state = self._create_game_state()
        result = self._tsumo(winner_seat=2)

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 1
        assert game_state.unique_dealers == 2

    def test_ron_dealer_wins_increments_honba(self):
        game_state = self._create_game_state()
        result = self._ron(winner_seat=0, loser_seat=1)

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 1

    def test_ron_dealer_loses_resets_honba_and_rotates(self):
        game_state = self._create_game_state()
        game_state.honba_sticks = 2
        result = self._ron(winner_seat=3, loser_seat=1)

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 0
        assert game_state.round_state.dealer_seat == 1
        assert game_state.unique_dealers == 2

    def test_double_ron_dealer_one_of_winners_increments_honba(self):
        game_state = self._create_game_state()
        result = DoubleRonResult(
            loser_seat=1,
            winners=[
                DoubleRonWinner(
                    winner_seat=0,
                    hand_result=HandResultInfo(han=1, fu=30, yaku=["Riichi"]),
                    riichi_sticks_collected=0,
                ),
                DoubleRonWinner(
                    winner_seat=2,
                    hand_result=HandResultInfo(han=1, fu=30, yaku=["Tanyao"]),
                    riichi_sticks_collected=0,
                ),
            ],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 1
        assert game_state.round_state.dealer_seat == 0

    def test_double_ron_dealer_not_winner_resets_honba_and_rotates(self):
        game_state = self._create_game_state()
        game_state.honba_sticks = 1
        result = DoubleRonResult(
            loser_seat=1,
            winners=[
                DoubleRonWinner(
                    winner_seat=2,
                    hand_result=HandResultInfo(han=1, fu=30, yaku=["Riichi"]),
                    riichi_sticks_collected=0,
                ),
                DoubleRonWinner(
                    winner_seat=3,
                    hand_result=HandResultInfo(han=1, fu=30, yaku=["Tanyao"]),
                    riichi_sticks_collected=0,
                ),
            ],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        process_round_end(game_state, result)

        assert game_state.honba_sticks == 0
        assert game_state.round_state.dealer_seat == 1
        assert game_state.unique_dealers == 2

    def test_round_number_increments(self):
        game_state = self._create_game_state()
        result = self._tsumo(winner_seat=0)

        process_round_end(game_state, result)

        assert game_state.round_number == 1

    def test_dealer_rotation_wraps_around(self):
        game_state = self._create_game_state()
        game_state.round_state.dealer_seat = 3
        result = self._tsumo(winner_seat=0)

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 0

    def test_wind_progression_stays_east(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 3
        result = self._tsumo(winner_seat=1)

        process_round_end(game_state, result)

        assert game_state.unique_dealers == 4
        assert game_state.round_state.round_wind == 0  # East

    def test_wind_progression_to_south(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 4
        result = self._tsumo(winner_seat=1)

        process_round_end(game_state, result)

        assert game_state.unique_dealers == 5
        assert game_state.round_state.round_wind == 1  # South

    def test_wind_progression_stays_south(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 7
        game_state.round_state.round_wind = 1
        result = self._tsumo(winner_seat=1)

        process_round_end(game_state, result)

        assert game_state.unique_dealers == 8
        assert game_state.round_state.round_wind == 1  # South

    def test_wind_progression_to_west(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 8
        game_state.round_state.round_wind = 1
        result = self._tsumo(winner_seat=1)

        process_round_end(game_state, result)

        assert game_state.unique_dealers == 9
        assert game_state.round_state.round_wind == 2  # West

    def test_nagashi_mangan_does_not_increment_honba(self):
        game_state = self._create_game_state()
        game_state.honba_sticks = 2
        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0, 1],
            noten_seats=[2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        process_round_end(game_state, result)

        # honba should remain unchanged (no increment for nagashi mangan)
        assert game_state.honba_sticks == 2

    def test_nagashi_mangan_dealer_tempai_does_not_rotate(self):
        game_state = self._create_game_state()
        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0],  # dealer (seat 0) is tempai
            noten_seats=[1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 0
        assert game_state.unique_dealers == 1

    def test_nagashi_mangan_dealer_noten_rotates(self):
        game_state = self._create_game_state()
        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[1],  # dealer (seat 0) is noten
            noten_seats=[0, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        process_round_end(game_state, result)

        assert game_state.round_state.dealer_seat == 1
        assert game_state.unique_dealers == 2


class TestCheckGameEnd:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="Bot1", score=25000),
            MahjongPlayer(seat=2, name="Bot2", score=25000),
            MahjongPlayer(seat=3, name="Bot3", score=25000),
        ]
        round_state = MahjongRoundState(players=players)
        return MahjongGameState(round_state=round_state, unique_dealers=1)

    def test_game_continues_normally(self):
        game_state = self._create_game_state()

        result = check_game_end(game_state)

        assert result is False

    def test_game_ends_player_negative_score(self):
        game_state = self._create_game_state()
        game_state.round_state.players[1].score = -1000

        result = check_game_end(game_state)

        assert result is True

    def test_game_ends_player_exactly_zero_continues(self):
        game_state = self._create_game_state()
        game_state.round_state.players[1].score = 0

        result = check_game_end(game_state)

        assert result is False

    def test_south_wind_complete_with_30000_ends(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 9  # south wind complete
        game_state.round_state.players[0].score = 30000

        result = check_game_end(game_state)

        assert result is True

    def test_south_wind_complete_without_30000_continues(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 9  # south wind complete
        # all players still at 25000

        result = check_game_end(game_state)

        assert result is False

    def test_south_wind_not_complete_with_30000_continues(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 8  # still in south
        game_state.round_state.players[0].score = 50000

        result = check_game_end(game_state)

        assert result is False

    def test_west_wind_complete_ends(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 13  # west wind complete

        result = check_game_end(game_state)

        assert result is True

    def test_west_wind_in_progress_continues(self):
        game_state = self._create_game_state()
        game_state.unique_dealers = 12  # still in west

        result = check_game_end(game_state)

        assert result is False


class TestFinalizeGame:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=30000),
            MahjongPlayer(seat=1, name="Bot1", score=25000),
            MahjongPlayer(seat=2, name="Bot2", score=25000),
            MahjongPlayer(seat=3, name="Bot3", score=20000),
        ]
        round_state = MahjongRoundState(players=players)
        return MahjongGameState(round_state=round_state, riichi_sticks=0)

    def test_winner_is_highest_score(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        assert result.winner_seat == 0

    def test_winner_tie_broken_by_lower_seat(self):
        game_state = self._create_game_state()
        game_state.round_state.players[0].score = 25000
        game_state.round_state.players[1].score = 30000
        game_state.round_state.players[2].score = 30000

        result = finalize_game(game_state)

        # seat 1 wins because lower seat
        assert result.winner_seat == 1

    def test_winner_gets_riichi_sticks(self):
        game_state = self._create_game_state()
        game_state.riichi_sticks = 2

        finalize_game(game_state)

        # winner (seat 0 with 30000) gets 2000 from riichi sticks
        assert game_state.round_state.players[0].score == 32000
        assert game_state.riichi_sticks == 0

    def test_riichi_sticks_cleared_after_distribution(self):
        game_state = self._create_game_state()
        game_state.riichi_sticks = 3

        finalize_game(game_state)

        assert game_state.riichi_sticks == 0

    def test_standings_sorted_by_score(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        standings = result.standings
        assert standings[0].seat == 0
        assert standings[0].score == 30000
        assert standings[1].seat == 1
        assert standings[1].score == 25000
        assert standings[2].seat == 2
        assert standings[2].score == 25000
        assert standings[3].seat == 3
        assert standings[3].score == 20000

    def test_standings_include_all_player_info(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        for standing in result.standings:
            assert standing.seat is not None
            assert standing.name is not None
            assert standing.score is not None
            assert standing.is_bot is not None

    def test_game_phase_set_to_finished(self):
        game_state = self._create_game_state()

        finalize_game(game_state)

        assert game_state.game_phase == GamePhase.FINISHED

    def test_result_type_is_game_end(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        assert result.type == "game_end"

    def test_standings_tied_scores_sorted_by_seat(self):
        game_state = self._create_game_state()
        # set all to same score
        for player in game_state.round_state.players:
            player.score = 25000

        result = finalize_game(game_state)

        standings = result.standings
        # should be in seat order when scores tied
        assert standings[0].seat == 0
        assert standings[1].seat == 1
        assert standings[2].seat == 2
        assert standings[3].seat == 3


class TestProcessDrawResultFallback:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="Bot1", score=25000),
            MahjongPlayer(seat=2, name="Bot2", score=25000),
            MahjongPlayer(seat=3, name="Bot3", score=25000),
        ]
        round_state = MahjongRoundState(players=players, dealer_seat=0, round_wind=0)
        return MahjongGameState(
            round_state=round_state,
            round_number=0,
            unique_dealers=1,
            honba_sticks=0,
            riichi_sticks=0,
        )

    def test_process_draw_result_fallback_returns_false(self):
        """Exhaustive draw type that is not an ExhaustiveDrawResult falls through to False."""
        game_state = self._create_game_state()
        # mock a result with EXHAUSTIVE_DRAW type but not an ExhaustiveDrawResult instance
        mock_result = MagicMock()
        mock_result.type = RoundResultType.EXHAUSTIVE_DRAW
        result = _process_draw_result(game_state, mock_result)
        assert result is False
        assert game_state.honba_sticks == 1


class TestProcessRoundEndFallback:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="Bot1", score=25000),
            MahjongPlayer(seat=2, name="Bot2", score=25000),
            MahjongPlayer(seat=3, name="Bot3", score=25000),
        ]
        round_state = MahjongRoundState(players=players, dealer_seat=0, round_wind=0)
        return MahjongGameState(
            round_state=round_state,
            round_number=0,
            unique_dealers=1,
            honba_sticks=0,
            riichi_sticks=0,
        )

    def test_process_round_end_unknown_result_type_does_not_rotate(self):
        """Unknown result type falls through to should_rotate=False."""
        game_state = self._create_game_state()
        mock_result = MagicMock()
        mock_result.type = "unknown_type"
        mock_result.tempai_seats = []
        process_round_end(game_state, mock_result)
        assert game_state.round_state.dealer_seat == 0
        assert game_state.unique_dealers == 1
        assert game_state.round_number == 1


class TestGoshashonyuRound:
    def test_positive_remainder_below_500_rounds_down(self):
        # 12300 -> 12.3 -> 12
        assert _goshashonyu_round(12300) == 12

    def test_positive_remainder_exactly_500_rounds_down(self):
        # 12500 -> 12.5 -> 12
        assert _goshashonyu_round(12500) == 12

    def test_positive_remainder_above_500_rounds_up(self):
        # 12600 -> 12.6 -> 13
        assert _goshashonyu_round(12600) == 13

    def test_positive_exact_thousands(self):
        # 12000 -> 12.0 -> 12
        assert _goshashonyu_round(12000) == 12

    def test_negative_remainder_below_500_rounds_toward_zero(self):
        # -1300 -> -1.3 -> -1
        assert _goshashonyu_round(-1300) == -1

    def test_negative_remainder_exactly_500_rounds_toward_zero(self):
        # -1500 -> -1.5 -> -1
        assert _goshashonyu_round(-1500) == -1

    def test_negative_remainder_above_500_rounds_away_from_zero(self):
        # -1900 -> -1.9 -> -2
        assert _goshashonyu_round(-1900) == -2

    def test_negative_remainder_600_rounds_away_from_zero(self):
        # -1600 -> -1.6 -> -2
        assert _goshashonyu_round(-1600) == -2

    def test_negative_exact_thousands(self):
        # -19000 -> -19.0 -> -19
        assert _goshashonyu_round(-19000) == -19

    def test_zero(self):
        assert _goshashonyu_round(0) == 0

    def test_positive_remainder_900(self):
        # 11900 -> 11.9 -> 12
        assert _goshashonyu_round(11900) == 12

    def test_negative_remainder_100(self):
        # -11100 -> -11.1 -> -11
        assert _goshashonyu_round(-11100) == -11


class TestCalculateFinalScores:
    def test_standard_case(self):
        # raw scores: P0=42300, P1=28100, P2=18600, P3=11000
        # diffs: +12300, -1900, -11400, -19000
        # goshashonyu: +12, -2, -11, -19
        # oka to 1st: +32, -2, -11, -19 (sum=0)
        # uma: +52, +8, -21, -39 (sum=0)
        raw = [(0, 42300), (1, 28100), (2, 18600), (3, 11000)]
        result = calculate_final_scores(raw)

        assert result == [(0, 52), (1, 8), (2, -21), (3, -39)]

    def test_zero_sum_invariant(self):
        raw = [(0, 42300), (1, 28100), (2, 18600), (3, 11000)]
        result = calculate_final_scores(raw)

        total = sum(score for _, score in result)
        assert total == 0

    def test_equal_scores_all_25000(self):
        # all 25000: diff = -5000 each
        # goshashonyu: -5 each
        # oka to 1st: +15, -5, -5, -5
        # uma: +35, +5, -15, -25 (sum=0)
        raw = [(0, 25000), (1, 25000), (2, 25000), (3, 25000)]
        result = calculate_final_scores(raw)

        assert result == [(0, 35), (1, 5), (2, -15), (3, -25)]
        assert sum(score for _, score in result) == 0

    def test_oka_only_applied_to_first_place(self):
        # verify 2nd, 3rd, 4th don't get oka bonus
        raw = [(0, 30000), (1, 30000), (2, 20000), (3, 20000)]
        result = calculate_final_scores(raw)

        # seat 0 (1st): diff=0, goshashonyu=0, +20 oka, +20 uma = 40
        # seat 1 (2nd): diff=0, goshashonyu=0, +10 uma = 10
        # seat 2 (3rd): diff=-10000, goshashonyu=-10, -10 uma = -20
        # seat 3 (4th): diff=-10000, goshashonyu=-10, -20 uma = -30
        # sum = 40 + 10 - 20 - 30 = 0
        assert result == [(0, 40), (1, 10), (2, -20), (3, -30)]

    def test_negative_raw_score(self):
        # player below zero
        raw = [(0, 55000), (1, 25000), (2, 25000), (3, -5000)]
        result = calculate_final_scores(raw)

        # seat 0: diff=25000, goshashonyu=25, +20 oka, +20 uma = 65
        # seat 1: diff=-5000, goshashonyu=-5, +10 uma = 5
        # seat 2: diff=-5000, goshashonyu=-5, -10 uma = -15
        # seat 3: diff=-35000, goshashonyu=-35, -20 uma = -55
        # sum = 65 + 5 - 15 - 55 = 0
        assert result == [(0, 65), (1, 5), (2, -15), (3, -55)]
        assert sum(score for _, score in result) == 0

    def test_goshashonyu_rounding_500_down_600_up(self):
        # test that 500 remainder rounds down and 600 rounds up
        # P0=30600 (diff=+600 -> 1), P1=30500 (diff=+500 -> 0)
        # P2=19500 (diff=-10500 -> -10), P3=19400 (diff=-10600 -> -11)
        raw = [(0, 30600), (1, 30500), (2, 19500), (3, 19400)]
        result = calculate_final_scores(raw)

        # seat 0: 1 + 20 oka + 20 uma = 41
        # seat 1: 0 + 10 uma = 10
        # seat 2: -10 + (-10) uma = -20
        # seat 3: -11 + (-20) uma = -31
        # sum = 41 + 10 - 20 - 31 = 0
        assert result == [(0, 41), (1, 10), (2, -20), (3, -31)]
        assert sum(score for _, score in result) == 0

    def test_zero_sum_adjustment_corrects_first_place(self):
        # create a case where rounding causes non-zero sum,
        # and 1st place gets adjusted
        # P0=30900, P1=30900, P2=19100, P3=19100
        # diffs: +900, +900, -10900, -10900
        # goshashonyu: +1, +1, -11, -11
        # sum before uma/oka = 1+1-11-11 = -20
        # oka to 1st: +21, +1, -11, -11, sum=-20+20=0
        # uma: +41, +11, -21, -31, sum=0
        raw = [(0, 30900), (1, 30900), (2, 19100), (3, 19100)]
        result = calculate_final_scores(raw)

        total = sum(score for _, score in result)
        assert total == 0

    def test_seat_order_preserved_in_output(self):
        raw = [(2, 42300), (0, 28100), (3, 18600), (1, 11000)]
        result = calculate_final_scores(raw)

        # seats should be in the same order as input
        assert result[0][0] == 2  # 1st place
        assert result[1][0] == 0  # 2nd place
        assert result[2][0] == 3  # 3rd place
        assert result[3][0] == 1  # 4th place


class TestFinalizeGameWithUmaOka:
    def _create_game_state(
        self,
        scores: list[int] | None = None,
    ) -> MahjongGameState:
        """Create a game state with specified scores."""
        if scores is None:
            scores = [42300, 28100, 18600, 11000]
        players = [
            MahjongPlayer(seat=0, name="Player1", score=scores[0]),
            MahjongPlayer(seat=1, name="Bot1", score=scores[1]),
            MahjongPlayer(seat=2, name="Bot2", score=scores[2]),
            MahjongPlayer(seat=3, name="Bot3", score=scores[3]),
        ]
        round_state = MahjongRoundState(players=players)
        return MahjongGameState(round_state=round_state, riichi_sticks=0)

    def test_standings_include_final_score(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        for standing in result.standings:
            assert standing.final_score is not None

    def test_final_scores_match_calculation(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        assert result.standings[0].final_score == 52
        assert result.standings[1].final_score == 8
        assert result.standings[2].final_score == -21
        assert result.standings[3].final_score == -39

    def test_final_scores_zero_sum(self):
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        total = sum(s.final_score for s in result.standings)
        assert total == 0

    def test_winner_determined_by_raw_scores(self):
        # winner is determined before uma/oka adjustment
        game_state = self._create_game_state()

        result = finalize_game(game_state)

        assert result.winner_seat == 0

    def test_riichi_sticks_distributed_before_final_score_calculation(self):
        game_state = self._create_game_state(scores=[42300, 28100, 18600, 11000])
        game_state.riichi_sticks = 2  # 2000 extra to winner

        result = finalize_game(game_state)

        # winner (seat 0) gets 2000 extra -> 44300
        assert result.standings[0].score == 44300
        assert game_state.riichi_sticks == 0
        # final scores include the riichi adjustment in raw score
        # seat 0: diff=14300, goshashonyu=14, +20 oka, +20 uma = 54 (before zero-sum)
        # others: 8, -21, -39 (unchanged), sum = 54+8-21-39 = 2, adj 1st = 52
        assert result.standings[0].final_score == 52
        assert sum(s.final_score for s in result.standings) == 0

    def test_tied_raw_scores_seat_order_determines_uma(self):
        # all 25000: seat order determines placement for uma
        game_state = self._create_game_state(scores=[25000, 25000, 25000, 25000])

        result = finalize_game(game_state)

        assert result.standings[0].seat == 0
        assert result.standings[1].seat == 1
        assert result.standings[2].seat == 2
        assert result.standings[3].seat == 3
        assert result.standings[0].final_score == 35
        assert result.standings[1].final_score == 5
        assert result.standings[2].final_score == -15
        assert result.standings[3].final_score == -25
