from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.settings import (
    WIND_THRESHOLDS,
    GameSettings,
    RenhouValue,
    build_optional_rules,
)


class TestWindThresholds:
    def test_wind_thresholds__should_be_4_8_12(self):
        east, south, west = WIND_THRESHOLDS
        assert east == 4
        assert south == 8
        assert west == 12


class TestBuildOptionalRules:
    def test_build_optional_rules__when_kazoe_yakuman_toggled__should_map_kazoe_limit(self):
        rules = build_optional_rules(GameSettings(has_kazoe_yakuman=True))
        assert rules.kazoe_limit == HandConfig.KAZOE_LIMITED
        rules = build_optional_rules(GameSettings(has_kazoe_yakuman=False))
        assert rules.kazoe_limit == HandConfig.KAZOE_SANBAIMAN

    def test_build_optional_rules__when_renhou_mangan__should_not_count_as_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.MANGAN))
        assert rules.renhou_as_yakuman is False

    def test_build_optional_rules__when_renhou_yakuman__should_count_as_yakuman(self):
        rules = build_optional_rules(GameSettings(renhou_value=RenhouValue.YAKUMAN))
        assert rules.renhou_as_yakuman is True
