from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mahjong.hand_calculating.hand_config import HandConfig


def _hand_config_debug(config: HandConfig) -> dict[str, object]:  # pragma: no cover
    options = config.options
    options_debug = None
    if options is not None:
        options_debug = {
            "has_open_tanyao": options.has_open_tanyao,
            "has_aka_dora": options.has_aka_dora,
            "has_double_yakuman": options.has_double_yakuman,
            "kazoe_limit": options.kazoe_limit,
            "kiriage": options.kiriage,
            "fu_for_open_pinfu": options.fu_for_open_pinfu,
            "fu_for_pinfu_tsumo": options.fu_for_pinfu_tsumo,
            "renhou_as_yakuman": options.renhou_as_yakuman,
            "has_daisharin": options.has_daisharin,
            "has_daisharin_other_suits": options.has_daisharin_other_suits,
            "has_daichisei": options.has_daichisei,
            "has_sashikomi_yakuman": options.has_sashikomi_yakuman,
            "limit_to_sextuple_yakuman": options.limit_to_sextuple_yakuman,
        }

    return {
        "is_tsumo": config.is_tsumo,
        "is_riichi": config.is_riichi,
        "is_ippatsu": config.is_ippatsu,
        "is_daburu_riichi": config.is_daburu_riichi,
        "is_rinshan": config.is_rinshan,
        "is_chankan": config.is_chankan,
        "is_haitei": config.is_haitei,
        "is_houtei": config.is_houtei,
        "is_tenhou": config.is_tenhou,
        "is_chiihou": config.is_chiihou,
        "is_renhou": config.is_renhou,
        "is_nagashi_mangan": config.is_nagashi_mangan,
        "player_wind": config.player_wind,
        "round_wind": config.round_wind,
        "is_dealer": config.is_dealer,
        "kyoutaku_number": config.kyoutaku_number,
        "tsumi_number": config.tsumi_number,
        "options": options_debug,
    }


def _melds_debug(  # pragma: no cover
    melds: list[Any] | tuple[Any, ...] | None,
) -> list[dict[str, object]] | None:
    if not melds:
        return None
    return [
        {
            "type": getattr(meld, "type", None),
            "opened": getattr(meld, "opened", None),
            "tiles": getattr(meld, "tiles", None),
            "called_tile": getattr(meld, "called_tile", None),
            "who": getattr(meld, "who", None),
            "from_who": getattr(meld, "from_who", None),
        }
        for meld in melds
    ]
