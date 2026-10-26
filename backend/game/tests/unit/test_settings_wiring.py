import pytest

from game.logic.exceptions import UnsupportedSettingsError
from game.logic.game import (
    _get_honba_and_rotation,
    check_game_end,
    init_game,
)
from game.logic.settings import (
    EnchousenType,
    GameSettings,
    GameType,
    RenhouValue,
    validate_settings,
)
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState
from game.logic.types import (
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    SeatConfig,
    TenpaiHand,
    YakuInfo,
)
from game.tests.conftest import create_game_state
from game.tests.helpers.wall import make_wall

# ============================================================================
# Settings Validation Tests
# ============================================================================


class TestValidateSettings:
    def test_validate_settings__when_renhou_baiman__should_raise(self):
        with pytest.raises(UnsupportedSettingsError, match="renhou_value=BAIMAN"):
            validate_settings(GameSettings(renhou_value=RenhouValue.BAIMAN))

    def test_validate_settings__when_tie_break_by_seat_order_false__should_raise_naming_it(self):
        with pytest.raises(UnsupportedSettingsError, match="tie_break_by_seat_order=False"):
            validate_settings(GameSettings(tie_break_by_seat_order=False))

    def test_validate_settings__when_several_unsupported_values__should_report_all(self):
        with pytest.raises(UnsupportedSettingsError, match=r"has_agariyame.*renhou_value=BAIMAN"):
            validate_settings(GameSettings(has_agariyame=True, renhou_value=RenhouValue.BAIMAN))

    @pytest.mark.parametrize(
        ("settings", "message"),
        [
            (GameSettings(min_wall_for_kan=1), "min_wall_for_kan must be at least 2"),
            (GameSettings(max_kans_per_round=5), "max_kans_per_round must be at most 4"),
        ],
    )
    def test_validate_settings__when_kan_limits_exceed_the_wall__should_raise(self, settings, message):
        with pytest.raises(UnsupportedSettingsError, match=message):
            validate_settings(settings)

    def test_validate_settings__when_uma_valid__should_pass(self):
        validate_settings(GameSettings(uma=(30, 10, -10, -30)))

    def test_init_game__when_settings_unsupported__should_raise(self):
        configs = [SeatConfig(name=f"Player{i}") for i in range(4)]
        with pytest.raises(UnsupportedSettingsError, match="has_agariyame"):
            init_game(configs, seed="a" * 192, settings=GameSettings(has_agariyame=True))


# ============================================================================
# Renchan Behavior Tests
# ============================================================================


class TestRenchanNagashiMangan:
    def test_renchan__when_nagashi_mangan_and_dealer_tempai_and_renchan_enabled__should_keep_dealer_and_add_honba(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=True)
        gs = create_game_state(honba_sticks=1, settings=settings)

        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        # Nagashi mangan increments honba same as exhaustive draw (1 → 2)
        assert honba == 2
        assert should_rotate is False

    def test_renchan__when_nagashi_mangan_and_dealer_tempai_and_renchan_disabled__should_rotate_and_add_honba(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=False)
        gs = create_game_state(honba_sticks=0, settings=settings)

        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        # Nagashi mangan increments honba same as exhaustive draw (0 → 1)
        assert honba == 1
        assert should_rotate is True


class TestRenchanDealerRonDisabled:
    def test_renchan__when_dealer_wins_by_ron_and_renchan_on_win_disabled__should_rotate(self):
        settings = GameSettings(renchan_on_dealer_win=False)
        gs = create_game_state(honba_sticks=0, settings=settings)

        result = RonResult(
            winner_seat=0,
            loser_seat=1,
            winning_tile=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000),
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
            riichi_sticks_collected=0,
            closed_tiles=[0, 1, 2],
            melds=[],
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 0
        assert should_rotate is True


# ============================================================================
# Game Type Tests
# ============================================================================


class TestGameTypeEnchousenExtensions:
    def _game_state(
        self,
        unique_dealers: int = 1,
        player_scores: list[int] | None = None,
        game_type: GameType = GameType.TONPUSEN,
        enchousen: EnchousenType = EnchousenType.SUDDEN_DEATH,
    ) -> MahjongGameState:
        scores = player_scores or [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        round_state = MahjongRoundState(wall=make_wall(), players=players)
        settings = GameSettings(game_type=game_type, enchousen=enchousen)
        return MahjongGameState(
            round_state=round_state,
            unique_dealers=unique_dealers,
            settings=settings,
        )

    def test_check_game_end__when_tonpusen_east_complete_without_winner__should_continue(self):
        gs = self._game_state(unique_dealers=5, player_scores=[25000, 25000, 25000, 25000])
        assert check_game_end(gs) is False

    def test_check_game_end__when_tonpusen_south_complete__should_end(self):
        gs = self._game_state(unique_dealers=9)
        assert check_game_end(gs) is True

    def test_check_game_end__when_hanchan_south_complete_without_winner__should_continue(self):
        gs = self._game_state(
            unique_dealers=9,
            player_scores=[25000, 25000, 25000, 25000],
            game_type=GameType.HANCHAN,
        )
        assert check_game_end(gs) is False

    def test_check_game_end__when_hanchan_west_complete__should_end(self):
        gs = self._game_state(unique_dealers=13, game_type=GameType.HANCHAN)
        assert check_game_end(gs) is True


# ============================================================================
# Enchousen Tests
# ============================================================================


class TestEnchousenNone:
    def _game_state(
        self,
        unique_dealers: int = 1,
        enchousen: EnchousenType = EnchousenType.NONE,
        game_type: GameType = GameType.HANCHAN,
    ) -> MahjongGameState:
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        round_state = MahjongRoundState(wall=make_wall(), players=players)
        settings = GameSettings(enchousen=enchousen, game_type=game_type)
        return MahjongGameState(
            round_state=round_state,
            unique_dealers=unique_dealers,
            settings=settings,
        )

    def test_check_game_end__when_enchousen_none_and_hanchan_south_complete__should_end(self):
        gs = self._game_state(unique_dealers=9, enchousen=EnchousenType.NONE)
        assert check_game_end(gs) is True

    def test_check_game_end__when_enchousen_none_and_tonpusen_east_complete__should_end(self):
        gs = self._game_state(
            unique_dealers=5,
            enchousen=EnchousenType.NONE,
            game_type=GameType.TONPUSEN,
        )
        assert check_game_end(gs) is True
