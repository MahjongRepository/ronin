from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.settings import (
    GameSettings,
    GameType,
    RenhouValue,
    build_optional_rules,
    get_wind_thresholds,
)


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
    def test_kazoe_yakuman_mapping(self):
        rules = build_optional_rules(GameSettings(has_kazoe_yakuman=True))
        assert rules.kazoe_limit == HandConfig.KAZOE_LIMITED
        rules = build_optional_rules(GameSettings(has_kazoe_yakuman=False))
        assert rules.kazoe_limit == HandConfig.KAZOE_SANBAIMAN

    def test_renhou_mangan_not_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.MANGAN))
        assert rules.renhou_as_yakuman is False

    def test_renhou_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.YAKUMAN))
        assert rules.renhou_as_yakuman is True

    def test_renhou_none_not_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.NONE))
        assert rules.renhou_as_yakuman is False
