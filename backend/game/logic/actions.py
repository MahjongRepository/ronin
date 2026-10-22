from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.abortive import can_call_kyuushu_kyuuhai
from game.logic.enums import PlayerAction
from game.logic.melds import get_possible_added_kans, get_possible_closed_kans
from game.logic.riichi import can_declare_riichi
from game.logic.types import AvailableActionItem
from game.logic.win import can_declare_tsumo

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


def get_available_actions(game_state: MahjongGameState, seat: int) -> list[AvailableActionItem]:
    """
    Return available actions for a player at their turn.

    The single source of a turn's offered actions, for the draw event and its reconnect rebuild alike. Discard is
    always available and handled implicitly by the client.

    Includes:
    - riichi option (if eligible)
    - tsumo option (if hand is winning and the player drew; never right after their own pon or chi)
    - kan options (closed and added)
    - kyuushu kyuuhai (if enabled and eligible on the player's first uninterrupted draw)
    """
    settings = game_state.settings
    round_state = game_state.round_state
    player = round_state.players[seat]

    result: list[AvailableActionItem] = []

    # check riichi eligibility
    if can_declare_riichi(player, round_state, settings=settings):
        result.append(AvailableActionItem(action=PlayerAction.RIICHI))

    # check tsumo
    if can_declare_tsumo(player, round_state, settings=settings):
        result.append(AvailableActionItem(action=PlayerAction.TSUMO))

    # check kan options
    closed_kans = get_possible_closed_kans(player, round_state, settings=settings)
    if closed_kans:
        result.append(AvailableActionItem(action=PlayerAction.KAN, tiles=closed_kans))

    added_kans = get_possible_added_kans(player, round_state, settings=settings)
    if added_kans:
        result.append(AvailableActionItem(action=PlayerAction.ADDED_KAN, tiles=added_kans))

    if can_call_kyuushu_kyuuhai(player, round_state, settings=settings):
        result.append(AvailableActionItem(action=PlayerAction.KYUUSHU))

    return result
