from __future__ import annotations

import json
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, model_validator

from game.logic.settings import (
    EnchousenType,
    GameSettings,
    GameType,
    LeftoverRiichiBets,
    RenhouValue,
    validate_settings,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class RuleProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    settings: GameSettings

    @model_validator(mode="after")
    def validate_complete_baseline(self) -> Self:
        missing = GameSettings.model_fields.keys() - self.settings.model_fields_set
        if missing:
            raise ValueError(f"rule profile {self.id} must explicitly define settings: {sorted(missing)}")

        validate_settings(self.settings)
        return self


STANDARD_RULE_PROFILE = RuleProfile(
    id=1,
    settings=GameSettings(
        game_type=GameType.HANCHAN,
        starting_score=25000,
        target_score=30000,
        winning_score_threshold=30000,
        uma=(20, 10, -10, -20),
        goshashonyu_threshold=500,
        tobi_enabled=True,
        tobi_threshold=0,
        has_akadora=True,
        has_kuitan=True,
        has_ippatsu=True,
        has_uradora=True,
        has_double_yakuman=True,
        has_kazoe_yakuman=True,
        has_kiriage_mangan=True,
        has_nagashi_mangan=True,
        renhou_value=RenhouValue.MANGAN,
        fu_for_open_pinfu=True,
        fu_for_pinfu_tsumo=False,
        has_daisharin=False,
        has_daisharin_other_suits=False,
        has_daichisei=False,
        limit_to_sextuple_yakuman=True,
        has_omote_dora=True,
        has_kandora=True,
        has_kan_uradora=True,
        kandora_immediate_for_closed_kan=True,
        kandora_deferred_for_open_kan=True,
        has_kuikae=True,
        has_kuikae_suji=True,
        min_wall_for_kan=2,
        max_kans_per_round=4,
        has_suukaikan=True,
        has_suufon_renda=True,
        has_suucha_riichi=True,
        has_kyuushu_kyuuhai=True,
        has_triple_ron_abort=True,
        kyuushu_min_types=9,
        min_players_for_kan_abort=2,
        four_winds_discard_count=4,
        has_double_ron=True,
        double_ron_count=2,
        has_agariyame=False,
        tie_break_by_seat_order=True,
        leftover_riichi_bets=LeftoverRiichiBets.WINNER,
        enchousen=EnchousenType.SUDDEN_DEATH,
        riichi_cost=1000,
        min_wall_for_riichi=4,
        riichi_stick_value=1000,
        honba_tsumo_bonus_per_loser=100,
        honba_ron_bonus=300,
        noten_penalty_total=3000,
        renchan_on_abortive_draw=True,
        renchan_on_dealer_tenpai_draw=True,
        renchan_on_dealer_win=True,
        nagashi_mangan_dealer_payment=4000,
        nagashi_mangan_non_dealer_payment=2000,
        has_daisangen_pao=True,
        has_daisuushii_pao=True,
    ),
)

RULE_PROFILES = MappingProxyType({profile.id: profile for profile in (STANDARD_RULE_PROFILE,)})


def get_rule_profile(profile_id: int) -> RuleProfile:
    profile = RULE_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"unknown rules profile: {profile_id}")

    return profile


def resolve_rule_profile(profile_id: int, overrides: Mapping[str, object]) -> GameSettings:
    profile = get_rule_profile(profile_id)
    merged = {**profile.settings.model_dump(mode="json"), **overrides}
    settings = GameSettings.model_validate_json(json.dumps(merged), strict=True)
    validate_settings(settings)
    return settings
