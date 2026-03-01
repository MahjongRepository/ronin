from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.settings import (
    WIND_THRESHOLDS,
    GameSettings,
    RenhouValue,
    build_optional_rules,
)


class TestWindThresholds:
    def test_four_players(self):
        east, south, west = WIND_THRESHOLDS
        assert east == 4
        assert south == 8
        assert west == 12


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
