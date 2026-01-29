"""
Available actions builder for Mahjong game.

Consolidates logic for determining what actions a player can take during their turn.
"""

from typing import TYPE_CHECKING

from game.logic.enums import PlayerAction
from game.logic.melds import get_possible_added_kans, get_possible_closed_kans
from game.logic.riichi import can_declare_riichi
from game.logic.types import AvailableActionItem
from game.logic.win import can_declare_tsumo

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongRoundState


def get_available_actions(
    round_state: MahjongRoundState,
    _game_state: MahjongGameState,
    seat: int,
) -> list[AvailableActionItem]:
    """
    Return available actions for a player at their turn.

    Includes:
    - discardable tiles
    - riichi option (if eligible)
    - tsumo option (if hand is winning)
    - kan options (closed and added)
    """
    player = round_state.players[seat]
    wall_count = len(round_state.wall)

    result: list[AvailableActionItem] = []

    # all tiles in hand can be discarded (unless in riichi)
    # in riichi, must discard the drawn tile (tsumogiri)
    discard_tiles = ([player.tiles[-1]] if player.tiles else []) if player.is_riichi else list(player.tiles)

    if discard_tiles:
        result.append(AvailableActionItem(action=PlayerAction.DISCARD, tiles=discard_tiles))

    # check riichi eligibility
    if can_declare_riichi(player, round_state):
        result.append(AvailableActionItem(action=PlayerAction.RIICHI))

    # check tsumo
    if can_declare_tsumo(player, round_state):
        result.append(AvailableActionItem(action=PlayerAction.TSUMO))

    # check kan options
    closed_kans = get_possible_closed_kans(player, wall_count)
    if closed_kans:
        result.append(AvailableActionItem(action=PlayerAction.KAN, tiles=closed_kans))

    added_kans = get_possible_added_kans(player, wall_count)
    if added_kans:
        result.append(AvailableActionItem(action=PlayerAction.ADDED_KAN, tiles=added_kans))

    return result
