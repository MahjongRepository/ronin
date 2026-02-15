"""
Riichi declaration and related mechanics for Mahjong game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.round import is_tempai
from game.logic.settings import GameSettings
from game.logic.state import MahjongPlayer
from game.logic.state_utils import update_player
from game.logic.wall import tiles_remaining

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongGameState,
        MahjongRoundState,
    )


def can_declare_riichi(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> bool:
    """
    Check if a player can declare riichi.

    Requirements:
    - Must not already be in riichi
    - Must be in tempai (one tile away from winning)
    - Must have closed hand (no open melds)
    - Must have at least 1000 points
    - Must have at least 4 tiles remaining in wall
    """
    # must not already be in riichi
    if player.is_riichi:
        return False

    # must have at least riichi_cost points
    if player.score < settings.riichi_cost:
        return False

    # must have closed hand (no open melds)
    if player.has_open_melds():
        return False

    # must have enough tiles remaining in wall
    if tiles_remaining(round_state.wall) < settings.min_wall_for_riichi:
        return False

    # must be in tempai
    return is_tempai(player.tiles, player.melds)


def declare_riichi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    settings: GameSettings,
) -> tuple[MahjongRoundState, MahjongGameState]:
    """
    Execute riichi declaration for a player.

    Sets riichi flags, deducts 1000 points, and increments riichi sticks.
    Should be called after validating with can_declare_riichi.

    Returns (new_round_state, new_game_state).
    """
    player = round_state.players[seat]

    # check for double riichi (daburi)
    # double riichi is possible if:
    # 1. this is the player's first discard (riichi discard already added, so len == 1)
    # 2. no open melds have been called by anyone
    is_daburi = len(player.discards) == 1 and len(round_state.players_with_open_hands) == 0

    new_round_state = update_player(
        round_state,
        seat,
        is_riichi=True,
        is_ippatsu=True,
        is_daburi=is_daburi,
        score=player.score - settings.riichi_cost,
    )

    new_game_state = game_state.model_copy(
        update={
            "riichi_sticks": game_state.riichi_sticks + 1,
            "round_state": new_round_state,
        }
    )

    return new_round_state, new_game_state
