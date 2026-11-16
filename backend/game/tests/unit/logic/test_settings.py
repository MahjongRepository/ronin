import hashlib
import json

import pytest
from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.rule_profiles import PRESET_SETTINGS, RuleProfile
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


class TestPresetRuleProfile:
    def test_rule_profile__when_defaults_would_fill_fields__should_require_explicit_baseline(self):
        with pytest.raises(ValueError, match="explicitly define settings"):
            RuleProfile(id=2, settings=GameSettings())

    def test_rule_profile__should_pin_the_preset_independently_of_defaults(self):
        normalized = json.dumps(PRESET_SETTINGS.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        assert (
            hashlib.sha256(normalized.encode()).hexdigest()
            == "c35fef2b4be543aa2eb74373a1993b35639eeb764ae0bb0c77a60f6be6a5c1eb"
        )
