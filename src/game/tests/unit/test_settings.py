import pytest
from mahjong.hand_calculating.hand_config import HandConfig
from pydantic import ValidationError

from game.logic.settings import (
    EnchousenType,
    GameSettings,
    GameType,
    LeftoverRiichiBets,
    RenhouValue,
    build_optional_rules,
    get_wind_thresholds,
)
from game.logic.timer import TimerConfig
from game.tests.conftest import create_game_state


class TestGameSettings:
    def test_default_settings_match_current_hardcoded_values(self):
        settings = GameSettings()
        assert settings.num_players == 4
        assert settings.game_type == GameType.HANCHAN
        assert settings.starting_score == 25000
        assert settings.target_score == 30000
        assert settings.winning_score_threshold == 30000
        assert settings.uma == (20, 10, -10, -20)
        assert settings.goshashonyu_threshold == 500
        assert settings.tobi_enabled is True
        assert settings.tobi_threshold == 0

    def test_default_yaku_hand_rules(self):
        settings = GameSettings()
        assert settings.has_akadora is True
        assert settings.has_kuitan is True
        assert settings.has_ippatsu is True
        assert settings.has_uradora is True
        assert settings.has_double_yakuman is True
        assert settings.has_kazoe_yakuman is True
        assert settings.has_kiriage_mangan is False
        assert settings.has_nagashi_mangan is True
        assert settings.renhou_value == RenhouValue.MANGAN
        assert settings.fu_for_open_pinfu is True
        assert settings.fu_for_pinfu_tsumo is False
        assert settings.has_daisharin is False
        assert settings.has_daisharin_other_suits is False
        assert settings.has_daichisei is False
        assert settings.has_sashikomi_yakuman is False
        assert settings.limit_to_sextuple_yakuman is True
        assert settings.paarenchan_needs_yaku is True

    def test_default_dora_rules(self):
        settings = GameSettings()
        assert settings.has_omote_dora is True
        assert settings.has_kandora is True
        assert settings.has_kan_uradora is True
        assert settings.kandora_immediate_for_closed_kan is True
        assert settings.kandora_deferred_for_open_kan is True

    def test_default_meld_rules(self):
        settings = GameSettings()
        assert settings.has_kuikae is True
        assert settings.has_kuikae_suji is True
        assert settings.min_wall_for_kan == 2
        assert settings.max_kans_per_round == 4

    def test_default_abortive_draw_rules(self):
        settings = GameSettings()
        assert settings.has_suukaikan is True
        assert settings.has_suufon_renda is True
        assert settings.has_suucha_riichi is True
        assert settings.has_kyuushu_kyuuhai is True
        assert settings.has_triple_ron_abort is True
        assert settings.kyuushu_min_types == 9
        assert settings.triple_ron_count == 3
        assert settings.min_players_for_kan_abort == 2
        assert settings.four_winds_discard_count == 4

    def test_default_win_rules(self):
        settings = GameSettings()
        assert settings.has_double_ron is True
        assert settings.double_ron_count == 2
        assert settings.has_agariyame is False
        assert settings.tie_break_by_seat_order is True
        assert settings.leftover_riichi_bets == LeftoverRiichiBets.WINNER
        assert settings.enchousen == EnchousenType.SUDDEN_DEATH

    def test_default_round_flow(self):
        settings = GameSettings()
        assert settings.riichi_cost == 1000
        assert settings.min_wall_for_riichi == 4
        assert settings.riichi_stick_value == 1000
        assert settings.honba_tsumo_bonus_per_loser == 100
        assert settings.honba_ron_bonus == 300
        assert settings.noten_penalty_total == 3000
        assert settings.renchan_on_abortive_draw is True
        assert settings.renchan_on_dealer_tenpai_draw is True
        assert settings.renchan_on_dealer_win is True
        assert settings.nagashi_mangan_dealer_payment == 4000
        assert settings.nagashi_mangan_non_dealer_payment == 2000

    def test_default_pao_rules(self):
        settings = GameSettings()
        assert settings.has_daisangen_pao is True
        assert settings.has_daisuushii_pao is True
        assert settings.daisangen_pao_set_threshold == 3
        assert settings.daisuushii_pao_set_threshold == 4

    def test_default_timer_settings(self):
        settings = GameSettings()
        assert settings.initial_bank_seconds == 3
        assert settings.round_bonus_seconds == 2
        assert settings.meld_decision_seconds == 2
        assert settings.round_advance_timeout_seconds == 15

    def test_frozen_model_cannot_be_mutated(self):
        settings = GameSettings()
        with pytest.raises(ValidationError):
            settings.starting_score = 30000
        with pytest.raises(ValidationError):
            settings.has_akadora = False

    def test_custom_settings(self):
        settings = GameSettings(
            game_type=GameType.TONPUSEN,
            starting_score=30000,
            has_akadora=False,
            has_kuitan=False,
        )
        assert settings.game_type == GameType.TONPUSEN
        assert settings.starting_score == 30000
        assert settings.has_akadora is False
        assert settings.has_kuitan is False
        # unchanged defaults
        assert settings.has_double_yakuman is True


class TestGetWindThresholds:
    def test_hanchan_four_players(self):
        settings = GameSettings(game_type=GameType.HANCHAN)
        east, south, west = get_wind_thresholds(settings)
        assert east == 4
        assert south == 8
        assert west == 12

    def test_tonpusen_four_players(self):
        settings = GameSettings(game_type=GameType.TONPUSEN)
        east, south, west = get_wind_thresholds(settings)
        assert east == 4
        assert south == 8
        assert west == 12

    def test_thresholds_scale_with_player_count(self):
        settings = GameSettings(num_players=3)
        east, south, west = get_wind_thresholds(settings)
        assert east == 3
        assert south == 6
        assert west == 9


class TestBuildOptionalRules:
    def test_default_settings_match_current_game_optional_rules(self):
        """Default settings produce the same OptionalRules as the current GAME_OPTIONAL_RULES constant."""
        settings = GameSettings()
        rules = build_optional_rules(settings)
        assert rules.has_aka_dora is True
        assert rules.has_open_tanyao is True
        assert rules.has_double_yakuman is True

    def test_akadora_mapping(self):
        rules = build_optional_rules(GameSettings(has_akadora=True))
        assert rules.has_aka_dora is True
        rules = build_optional_rules(GameSettings(has_akadora=False))
        assert rules.has_aka_dora is False

    def test_kuitan_mapping(self):
        rules = build_optional_rules(GameSettings(has_kuitan=True))
        assert rules.has_open_tanyao is True
        rules = build_optional_rules(GameSettings(has_kuitan=False))
        assert rules.has_open_tanyao is False

    def test_double_yakuman_mapping(self):
        rules = build_optional_rules(GameSettings(has_double_yakuman=True))
        assert rules.has_double_yakuman is True
        rules = build_optional_rules(GameSettings(has_double_yakuman=False))
        assert rules.has_double_yakuman is False

    def test_kazoe_yakuman_mapping(self):
        rules = build_optional_rules(GameSettings(has_kazoe_yakuman=True))
        assert rules.kazoe_limit == HandConfig.KAZOE_LIMITED
        rules = build_optional_rules(GameSettings(has_kazoe_yakuman=False))
        assert rules.kazoe_limit == HandConfig.KAZOE_SANBAIMAN

    def test_kiriage_mangan_mapping(self):
        rules = build_optional_rules(GameSettings(has_kiriage_mangan=False))
        assert rules.kiriage is False
        rules = build_optional_rules(GameSettings(has_kiriage_mangan=True))
        assert rules.kiriage is True

    def test_renhou_mangan_not_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.MANGAN))
        assert rules.renhou_as_yakuman is False

    def test_renhou_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.YAKUMAN))
        assert rules.renhou_as_yakuman is True

    def test_renhou_none_not_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.NONE))
        assert rules.renhou_as_yakuman is False

    def test_fu_for_open_pinfu_mapping(self):
        rules = build_optional_rules(GameSettings(fu_for_open_pinfu=True))
        assert rules.fu_for_open_pinfu is True
        rules = build_optional_rules(GameSettings(fu_for_open_pinfu=False))
        assert rules.fu_for_open_pinfu is False

    def test_fu_for_pinfu_tsumo_mapping(self):
        rules = build_optional_rules(GameSettings(fu_for_pinfu_tsumo=False))
        assert rules.fu_for_pinfu_tsumo is False
        rules = build_optional_rules(GameSettings(fu_for_pinfu_tsumo=True))
        assert rules.fu_for_pinfu_tsumo is True

    def test_daisharin_mapping(self):
        rules = build_optional_rules(GameSettings(has_daisharin=False))
        assert rules.has_daisharin is False
        rules = build_optional_rules(GameSettings(has_daisharin=True))
        assert rules.has_daisharin is True

    def test_daisharin_other_suits_mapping(self):
        rules = build_optional_rules(GameSettings(has_daisharin_other_suits=False))
        assert rules.has_daisharin_other_suits is False
        rules = build_optional_rules(GameSettings(has_daisharin_other_suits=True))
        assert rules.has_daisharin_other_suits is True

    def test_daichisei_mapping(self):
        rules = build_optional_rules(GameSettings(has_daichisei=False))
        assert rules.has_daichisei is False
        rules = build_optional_rules(GameSettings(has_daichisei=True))
        assert rules.has_daichisei is True

    def test_sashikomi_yakuman_mapping(self):
        rules = build_optional_rules(GameSettings(has_sashikomi_yakuman=False))
        assert rules.has_sashikomi_yakuman is False
        rules = build_optional_rules(GameSettings(has_sashikomi_yakuman=True))
        assert rules.has_sashikomi_yakuman is True

    def test_limit_to_sextuple_yakuman_mapping(self):
        rules = build_optional_rules(GameSettings(limit_to_sextuple_yakuman=True))
        assert rules.limit_to_sextuple_yakuman is True
        rules = build_optional_rules(GameSettings(limit_to_sextuple_yakuman=False))
        assert rules.limit_to_sextuple_yakuman is False

    def test_paarenchan_needs_yaku_mapping(self):
        rules = build_optional_rules(GameSettings(paarenchan_needs_yaku=True))
        assert rules.paarenchan_needs_yaku is True
        rules = build_optional_rules(GameSettings(paarenchan_needs_yaku=False))
        assert rules.paarenchan_needs_yaku is False


class TestSettingsPropagation:
    def test_settings_propagated_to_game_state_via_conftest(self):
        """Settings passed to create_game_state are stored on game_state."""
        custom = GameSettings(starting_score=30000, riichi_cost=2000)
        gs = create_game_state(settings=custom)
        assert gs.settings is custom

    def test_default_settings_on_game_state(self):
        gs = create_game_state()
        assert gs.settings == GameSettings()


class TestTimerConfigFromSettings:
    def test_from_default_settings(self):
        settings = GameSettings()
        config = TimerConfig.from_settings(settings)
        assert config.initial_bank_seconds == 3
        assert config.round_bonus_seconds == 2
        assert config.meld_decision_seconds == 2

    def test_from_custom_settings(self):
        settings = GameSettings(
            initial_bank_seconds=10,
            round_bonus_seconds=5,
            meld_decision_seconds=3,
        )
        config = TimerConfig.from_settings(settings)
        assert config.initial_bank_seconds == 10
        assert config.round_bonus_seconds == 5
        assert config.meld_decision_seconds == 3

    def test_round_advance_timeout_from_settings(self):
        """round_advance_timeout_seconds is read from GameSettings by timer_manager."""
        settings = GameSettings(round_advance_timeout_seconds=20)
        assert settings.round_advance_timeout_seconds == 20


class TestEnums:
    def test_game_type_values(self):
        assert GameType.HANCHAN == "hanchan"
        assert GameType.TONPUSEN == "tonpusen"

    def test_renhou_value_values(self):
        assert RenhouValue.NONE == "none"
        assert RenhouValue.MANGAN == "mangan"
        assert RenhouValue.BAIMAN == "baiman"
        assert RenhouValue.YAKUMAN == "yakuman"

    def test_enchousen_type_values(self):
        assert EnchousenType.NONE == "none"
        assert EnchousenType.SUDDEN_DEATH == "sudden_death"

    def test_leftover_riichi_bets_values(self):
        assert LeftoverRiichiBets.WINNER == "winner"
        assert LeftoverRiichiBets.LOST == "lost"
