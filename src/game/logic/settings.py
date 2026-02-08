"""Centralized game settings for Mahjong - all configurable gameplay rules."""

from __future__ import annotations

from enum import Enum

from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from pydantic import BaseModel, ConfigDict

from game.logic.exceptions import UnsupportedSettingsError


class GameType(str, Enum):
    """Game length type."""

    HANCHAN = "hanchan"  # East + South
    TONPUSEN = "tonpusen"  # East only


class RenhouValue(str, Enum):
    """Renhou scoring level."""

    NONE = "none"
    MANGAN = "mangan"  # 5-han (current default, supported by mahjong library)
    BAIMAN = "baiman"  # 8-han (requires custom implementation, NOT YET SUPPORTED)
    YAKUMAN = "yakuman"  # yakuman (supported via library's renhou_as_yakuman flag)


class EnchousenType(str, Enum):
    """Extension round behavior after South wind."""

    NONE = "none"
    SUDDEN_DEATH = "sudden_death"  # West wind until someone exceeds target


class LeftoverRiichiBets(str, Enum):
    """What happens to uncollected riichi bets at game end."""

    WINNER = "winner"  # Top player collects them
    LOST = "lost"  # They disappear


class GameSettings(BaseModel):
    """
    Centralized configuration for all Mahjong game rules.

    All fields have default values matching the current hardcoded behavior.
    """

    model_config = ConfigDict(frozen=True)

    # --- Game Structure ---
    num_players: int = 4
    game_type: GameType = GameType.HANCHAN
    starting_score: int = 25000
    target_score: int = 30000
    winning_score_threshold: int = 30000

    # --- Scoring ---
    uma: tuple[int, ...] = (20, 10, -10, -20)
    goshashonyu_threshold: int = 500
    tobi_enabled: bool = True
    tobi_threshold: int = 0

    # --- Yaku / Hand Rules ---
    has_akadora: bool = True
    has_kuitan: bool = True
    has_ippatsu: bool = True
    has_uradora: bool = True
    has_double_yakuman: bool = True
    has_kazoe_yakuman: bool = True
    has_kiriage_mangan: bool = False
    has_nagashi_mangan: bool = True
    renhou_value: RenhouValue = RenhouValue.MANGAN
    fu_for_open_pinfu: bool = True
    fu_for_pinfu_tsumo: bool = False
    has_daisharin: bool = False
    has_daisharin_other_suits: bool = False
    has_daichisei: bool = False
    has_sashikomi_yakuman: bool = False
    limit_to_sextuple_yakuman: bool = True
    paarenchan_needs_yaku: bool = True

    # --- Dora Rules ---
    has_omote_dora: bool = True
    has_kandora: bool = True
    has_kan_uradora: bool = True
    kandora_immediate_for_closed_kan: bool = True
    kandora_deferred_for_open_kan: bool = True

    # --- Meld Rules ---
    has_kuikae: bool = True
    has_kuikae_suji: bool = True
    min_wall_for_kan: int = 2
    max_kans_per_round: int = 4

    # --- Abortive Draw Rules ---
    has_suukaikan: bool = True
    has_suufon_renda: bool = True
    has_suucha_riichi: bool = True
    has_kyuushu_kyuuhai: bool = True
    has_triple_ron_abort: bool = True
    kyuushu_min_types: int = 9
    triple_ron_count: int = 3
    min_players_for_kan_abort: int = 2
    four_winds_discard_count: int = 4

    # --- Win Rules ---
    has_double_ron: bool = True
    double_ron_count: int = 2
    has_agariyame: bool = False
    tie_break_by_seat_order: bool = True
    leftover_riichi_bets: LeftoverRiichiBets = LeftoverRiichiBets.WINNER
    enchousen: EnchousenType = EnchousenType.SUDDEN_DEATH

    # --- Round Flow ---
    riichi_cost: int = 1000
    min_wall_for_riichi: int = 4
    riichi_stick_value: int = 1000
    honba_tsumo_bonus_per_loser: int = 100
    honba_ron_bonus: int = 300
    noten_penalty_total: int = 3000
    renchan_on_abortive_draw: bool = True
    renchan_on_dealer_tenpai_draw: bool = True
    renchan_on_dealer_win: bool = True
    nagashi_mangan_dealer_payment: int = 4000
    nagashi_mangan_non_dealer_payment: int = 2000

    # --- Pao Rules ---
    has_daisangen_pao: bool = True
    has_daisuushii_pao: bool = True
    daisangen_pao_set_threshold: int = 3
    daisuushii_pao_set_threshold: int = 4

    # --- Timer / Round Pacing Settings ---
    initial_bank_seconds: float = 3
    round_bonus_seconds: float = 2
    meld_decision_seconds: float = 2
    round_advance_timeout_seconds: float = 15


SUPPORTED_NUM_PLAYERS = 4


def validate_settings(settings: GameSettings) -> None:
    """Validate that all settings values are supported by the engine.

    Raises UnsupportedSettingsError for any setting value that is defined
    but not yet implemented in runtime logic.
    """
    errors: list[str] = []

    if settings.num_players != SUPPORTED_NUM_PLAYERS:
        errors.append(f"num_players={settings.num_players} is not supported (only 4-player games)")

    if settings.has_agariyame:
        errors.append("has_agariyame=True is not supported (agariyame not yet implemented)")

    if settings.renhou_value == RenhouValue.BAIMAN:
        errors.append("renhou_value=BAIMAN is not supported (requires custom 8-han scoring)")

    if not settings.tie_break_by_seat_order:
        errors.append("tie_break_by_seat_order=False is not supported (no alternative tie-break strategy)")

    if errors:
        raise UnsupportedSettingsError("; ".join(errors))


def get_wind_thresholds(settings: GameSettings) -> tuple[int, int, int]:
    """Compute (east_max, south_max, west_max) dealer thresholds.

    Returns raw boundaries based on num_players. The caller (check_game_end)
    selects which threshold is the primary wind boundary based on game_type.
    """
    n = settings.num_players
    return (n, n * 2, n * 3)


def build_optional_rules(settings: GameSettings) -> OptionalRules:
    """Build mahjong library OptionalRules from GameSettings."""
    return OptionalRules(
        has_aka_dora=settings.has_akadora,
        has_open_tanyao=settings.has_kuitan,
        has_double_yakuman=settings.has_double_yakuman,
        kiriage=settings.has_kiriage_mangan,
        kazoe_limit=(HandConfig.KAZOE_LIMITED if settings.has_kazoe_yakuman else HandConfig.KAZOE_SANBAIMAN),
        renhou_as_yakuman=settings.renhou_value == RenhouValue.YAKUMAN,
        fu_for_open_pinfu=settings.fu_for_open_pinfu,
        fu_for_pinfu_tsumo=settings.fu_for_pinfu_tsumo,
        has_daisharin=settings.has_daisharin,
        has_daisharin_other_suits=settings.has_daisharin_other_suits,
        has_daichisei=settings.has_daichisei,
        has_sashikomi_yakuman=settings.has_sashikomi_yakuman,
        limit_to_sextuple_yakuman=settings.limit_to_sextuple_yakuman,
        paarenchan_needs_yaku=settings.paarenchan_needs_yaku,
    )
