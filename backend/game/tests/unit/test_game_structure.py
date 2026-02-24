"""
Verify that game type, player count, scores, uma, oka, tobi, and agariyame
settings are properly configurable and not hardcoded in game logic.
"""

import pytest

from game.logic.exceptions import UnsupportedSettingsError
from game.logic.game import (
    calculate_final_scores,
    check_game_end,
    finalize_game,
    init_game,
)
from game.logic.settings import (
    GameSettings,
    GameType,
    validate_settings,
)
from game.logic.types import SeatConfig
from game.tests.conftest import create_game_state, create_player, create_round_state


class TestGameType:
    """Verify game_type setting controls wind progression and game-end."""

    def test_hanchan_primary_wind_completes_after_south(self):
        """Hanchan: game does NOT end after East wind (unique_dealers=5), continues to South."""
        players = tuple(create_player(seat=i, score=35000) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=5,
            settings=GameSettings(game_type=GameType.HANCHAN),
        )
        # unique_dealers=5 means East is done, entering South — primary wind NOT complete yet
        assert check_game_end(game_state) is False

    def test_hanchan_ends_after_south_with_winner(self):
        """Hanchan: game ends after South wind when a player has threshold score."""
        players = tuple(create_player(seat=i, score=35000 if i == 0 else 21667) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=9,  # South complete
            settings=GameSettings(game_type=GameType.HANCHAN),
        )
        assert check_game_end(game_state) is True

    def test_tonpusen_ends_after_east_with_winner(self):
        """Tonpusen: game ends after East wind when a player has threshold score."""
        players = tuple(create_player(seat=i, score=35000 if i == 0 else 21667) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=5,  # East complete
            settings=GameSettings(game_type=GameType.TONPUSEN),
        )
        assert check_game_end(game_state) is True

    def test_tonpusen_does_not_end_during_east(self):
        """Tonpusen: game does NOT end during East wind even with high scores."""
        players = tuple(create_player(seat=i, score=50000 if i == 0 else 16667) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=3,  # still in East
            settings=GameSettings(game_type=GameType.TONPUSEN),
        )
        assert check_game_end(game_state) is False


class TestNumPlayers:
    """Verify num_players setting exists and is validated."""

    def test_validate_rejects_non_4_num_players(self):
        settings = GameSettings(num_players=3)
        with pytest.raises(UnsupportedSettingsError, match="num_players=3 is not supported"):
            validate_settings(settings)


class TestStartingScore:
    """Verify starting_score setting is used from settings, not hardcoded."""

    def test_custom_starting_score_in_init_game(self):
        """Players start with the configured starting_score, not hardcoded 25000."""
        seat_configs = [SeatConfig(name=f"P{i}") for i in range(4)]
        wall = list(range(136))
        game_state = init_game(seat_configs, settings=GameSettings(starting_score=30000), wall=wall)
        for player in game_state.round_state.players:
            assert player.score == 30000

    def test_starting_score_affects_oka_calculation(self):
        """Oka = (target - starting) * num_players / 1000."""
        # With starting=20000, target=30000: oka = (30000-20000)*4/1000 = 40
        # Raw scores summing to starting*4 = 80000
        raw = [(0, 35000), (1, 25000), (2, 15000), (3, 5000)]
        settings = GameSettings(starting_score=20000, target_score=30000)
        result = calculate_final_scores(raw, settings)
        # 1st: diff=5 + oka=40 + uma=20 = 65
        assert result[0][1] == 65


class TestTargetScore:
    """Verify target_score setting is used in oka and final score adjustment."""

    def test_custom_target_score_shifts_final_scores(self):
        """Final scores are calculated relative to target_score."""
        raw = [(0, 40000), (1, 30000), (2, 20000), (3, 10000)]
        settings = GameSettings(target_score=25000, starting_score=25000)
        result = calculate_final_scores(raw, settings)
        # target=starting, so oka=0
        # diff from target: +15, +5, -5, -15
        # uma: +20, +10, -10, -20
        # adjusted: 35, 15, -15, -35
        assert result == [(0, 35), (1, 15), (2, -15), (3, -35)]
        assert sum(s for _, s in result) == 0


class TestWinningScoreThreshold:
    """Verify winning_score_threshold is distinct from target_score."""

    def test_threshold_distinct_from_target_score(self):
        """Game ends based on winning_score_threshold, not target_score."""
        # Set high threshold: even 35000 doesn't end the game
        players = tuple(create_player(seat=i, score=35000 if i == 0 else 21667) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=9,  # post-South (hanchan primary complete)
            settings=GameSettings(
                target_score=30000,
                winning_score_threshold=40000,
            ),
        )
        # 35000 < 40000, so game continues into West
        assert check_game_end(game_state) is False

    def test_custom_low_threshold_ends_game_early(self):
        """Lower threshold ends game sooner after primary wind."""
        players = tuple(create_player(seat=i, score=26000 if i == 0 else 24667) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=9,
            settings=GameSettings(winning_score_threshold=25000),
        )
        # 26000 >= 25000, game ends
        assert check_game_end(game_state) is True


class TestUma:
    """Verify uma setting is applied correctly in final score calculation."""

    def test_custom_uma_applied_to_final_scores(self):
        """Custom uma spread changes final placement rewards/penalties."""
        raw = [(0, 30000), (1, 30000), (2, 20000), (3, 20000)]
        settings = GameSettings(uma=(30, 10, -10, -30))
        result = calculate_final_scores(raw, settings)
        # default oka=20 (target=30000, starting=25000)
        # seat0: diff=0 + oka=20 + uma=30 = 50
        # seat1: diff=0 + uma=10 = 10
        # seat2: diff=-10 + uma=-10 = -20
        # seat3: diff=-10 + uma=-30 = -40
        # zero-sum adjust on 1st: sum=0 → no adjustment
        assert result == [(0, 50), (1, 10), (2, -20), (3, -40)]
        assert sum(s for _, s in result) == 0

    def test_validate_rejects_wrong_length_uma(self):
        settings = GameSettings(uma=(20, 10, -30))
        with pytest.raises(UnsupportedSettingsError, match="uma must have 4 entries"):
            validate_settings(settings)

    def test_validate_rejects_nonzero_sum_uma(self):
        settings = GameSettings(uma=(20, 10, -10, -10))
        with pytest.raises(UnsupportedSettingsError, match="uma values must sum to zero"):
            validate_settings(settings)


class TestOkaCalculation:
    """Verify oka is correctly derived from target_score and starting_score."""

    def test_standard_oka_25k_30k(self):
        """Default: oka = (30000-25000)*4/1000 = 20 points to 1st place."""
        raw = [(0, 30000), (1, 30000), (2, 20000), (3, 20000)]
        result = calculate_final_scores(raw, GameSettings())
        # 1st: diff=0 + oka=20 + uma=20 = 40
        assert result[0][1] == 40

    def test_no_oka_when_starting_equals_target(self):
        """When starting_score == target_score, oka is 0."""
        # Raw scores summing to starting*4 = 120000
        raw = [(0, 40000), (1, 30000), (2, 30000), (3, 20000)]
        settings = GameSettings(starting_score=30000, target_score=30000)
        result = calculate_final_scores(raw, settings)
        # 1st: diff=10 + oka=0 + uma=20 = 30
        assert result[0][1] == 30

    def test_large_oka_with_big_gap(self):
        """Larger gap between starting and target produces larger oka."""
        # starting=10000, target=50000: oka = (50000-10000)*4/1000 = 160
        # Raw scores summing to starting*4 = 40000
        raw = [(0, 20000), (1, 10000), (2, 5000), (3, 5000)]
        settings = GameSettings(starting_score=10000, target_score=50000)
        result = calculate_final_scores(raw, settings)
        # 1st: diff=-30 + oka=160 + uma=20 = 150
        assert result[0][1] == 150


class TestTobi:
    """Verify tobi (bankruptcy) game-end behavior."""

    def test_tobi_ends_game_when_score_below_zero(self):
        """Player with negative score triggers game end when tobi is enabled."""
        players = tuple(create_player(seat=i, score=-100 if i == 3 else 33367) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=1,  # still in East round 1
            settings=GameSettings(tobi_enabled=True),
        )
        assert check_game_end(game_state) is True

    def test_tobi_does_not_trigger_at_zero(self):
        """Score of exactly 0 does NOT trigger tobi (threshold is strict <)."""
        players = tuple(create_player(seat=i, score=0 if i == 3 else 33334) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=1,
            settings=GameSettings(tobi_enabled=True),
        )
        assert check_game_end(game_state) is False

    def test_tobi_disabled_ignores_negative_score(self):
        """When tobi is disabled, negative scores do not end the game."""
        players = tuple(create_player(seat=i, score=-5000 if i == 3 else 35000) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(
            round_state,
            unique_dealers=1,
            settings=GameSettings(tobi_enabled=False),
        )
        assert check_game_end(game_state) is False

    def test_custom_tobi_threshold(self):
        """Custom tobi_threshold changes the bankruptcy boundary."""
        players = tuple(create_player(seat=i, score=500 if i == 3 else 33167) for i in range(4))
        round_state = create_round_state(players=players)
        # threshold=1000: score of 500 < 1000 triggers tobi
        game_state = create_game_state(
            round_state,
            unique_dealers=1,
            settings=GameSettings(tobi_enabled=True, tobi_threshold=1000),
        )
        assert check_game_end(game_state) is True


class TestAgariyame:
    """Verify agariyame setting exists and is validated as unsupported."""

    def test_validate_rejects_agariyame_enabled(self):
        settings = GameSettings(has_agariyame=True)
        with pytest.raises(UnsupportedSettingsError, match="has_agariyame=True is not supported"):
            validate_settings(settings)


class TestFinalizeGamePlacement:
    """Verify finalize_game uses settings correctly for placement."""

    def test_finalize_uses_starting_score_and_target_from_settings(self):
        """Final scores use the settings' starting_score and target_score."""
        players = tuple(create_player(seat=i, score=score) for i, score in enumerate([40000, 30000, 20000, 10000]))
        round_state = create_round_state(players=players)
        settings = GameSettings(starting_score=25000, target_score=25000)
        game_state = create_game_state(round_state, settings=settings)

        _, result = finalize_game(game_state)
        # With target==starting, oka=0
        # Standings should be in order: seat 0, 1, 2, 3
        assert result.winner_seat == 0
        assert result.standings[0].seat == 0
        assert result.standings[3].seat == 3
        # Zero-sum check on final scores
        assert sum(s.final_score for s in result.standings) == 0
