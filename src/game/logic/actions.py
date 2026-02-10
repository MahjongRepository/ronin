"""
Available actions builder for Mahjong game.

Consolidates logic for determining what actions a player can take during their turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.enums import PlayerAction
from game.logic.melds import get_possible_added_kans, get_possible_closed_kans
from game.logic.riichi import can_declare_riichi
from game.logic.types import AvailableActionItem
from game.logic.win import can_declare_tsumo

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongGameState,
        MahjongRoundState,
    )


def get_available_actions(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> list[AvailableActionItem]:
    """
    Return available actions for a player at their turn.

    Discard is always available and handled implicitly by the client.

    Includes:
    - riichi option (if eligible)
    - tsumo option (if hand is winning)
    - kan options (closed and added)
    """
    settings = game_state.settings
    player = round_state.players[seat]

    result: list[AvailableActionItem] = []

    # check riichi eligibility
    if can_declare_riichi(player, round_state, settings):
        result.append(AvailableActionItem(action=PlayerAction.RIICHI))

    # check tsumo
    if can_declare_tsumo(player, round_state, settings):
        result.append(AvailableActionItem(action=PlayerAction.TSUMO))

    # check kan options
    closed_kans = get_possible_closed_kans(player, round_state, settings)
    if closed_kans:
        result.append(AvailableActionItem(action=PlayerAction.KAN, tiles=closed_kans))

    added_kans = get_possible_added_kans(player, round_state, settings)
    if added_kans:
        result.append(AvailableActionItem(action=PlayerAction.ADDED_KAN, tiles=added_kans))

    return result
