"""
Unit tests for game initialization and progression.
"""

from game.logic.enums import AbortiveDrawType, BotType
from game.logic.game import (
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
    RonResult,
    SeatConfig,
    TsumoResult,
)


def _default_seat_configs() -> list[SeatConfig]:
    """Create standard seat configs for testing: 1 human + 3 bots."""
    return [
        SeatConfig(name="Human", is_bot=False),
        SeatConfig(name="Tsumogiri 1", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", is_bot=True, bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", is_bot=True, bot_type=BotType.TSUMOGIRI),
    ]


class TestInitGame:
    def test_init_game_creates_four_players(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert len(game_state.round_state.players) == 4

    def test_init_game_first_player_is_human(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        assert game_state.round_state.players[0].is_bot is False
        assert game_state.round_state.players[0].name == "Human"

    def test_init_game_other_players_are_bots(self):
        configs = _default_seat_configs()
        game_state = init_game(configs)

        for i in range(1, 4):
            assert game_state.round_state.players[i].is_bot is True

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
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, score=25000),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, score=25000),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, score=25000),
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


class TestCheckGameEnd:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, score=25000),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, score=25000),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, score=25000),
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
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, score=25000),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, score=25000),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, score=20000),
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
