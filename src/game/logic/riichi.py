"""
Riichi declaration and related mechanics for Mahjong game.
"""

from typing import TYPE_CHECKING

from game.logic.round import is_tempai

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState

# ura dora positions in dead wall: indices 9, 10, 11, 12 (one per dora indicator)
FIRST_URA_DORA_INDEX = 9

# riichi point cost
RIICHI_COST = 1000


def can_declare_riichi(player: MahjongPlayer, round_state: MahjongRoundState) -> bool:
    """
    Check if a player can declare riichi.

    Requirements:
    - Must not already be in riichi
    - Must be in tempai (one tile away from winning)
    - Must have closed hand (no open melds)
    - Must have at least 1000 points
    - Must have at least one tile remaining in wall
    """
    # must not already be in riichi
    if player.is_riichi:
        return False

    # must have at least 1000 points
    if player.score < RIICHI_COST:
        return False

    # must have closed hand (no open melds)
    if player.has_open_melds():
        return False

    # must have tiles remaining in wall
    if len(round_state.wall) == 0:
        return False

    # must be in tempai
    return is_tempai(player)


def declare_riichi(player: MahjongPlayer, game_state: MahjongGameState) -> None:
    """
    Execute riichi declaration for a player.

    Sets riichi flags, deducts 1000 points, and increments riichi sticks.
    Should be called after validating with can_declare_riichi.
    """
    round_state = game_state.round_state

    # set riichi flag
    player.is_riichi = True

    # check for double riichi (daburi)
    # double riichi is possible if:
    # 1. this is the player's first discard (riichi discard already added, so len == 1)
    # 2. no open melds have been called by anyone
    if len(player.discards) == 1 and len(round_state.players_with_open_hands) == 0:
        player.is_daburi = True

    # set ippatsu flag (cleared after any discard or meld call)
    player.is_ippatsu = True

    # deduct 1000 points
    player.score -= 1000

    # increment riichi sticks
    game_state.riichi_sticks += 1


def get_ura_dora(round_state: MahjongRoundState, num_dora: int) -> list[int]:
    """
    Get ura dora tiles revealed when winning with riichi.

    The ura dora indicators are at dead wall indices 9, 10, 11, 12.
    One ura dora is revealed per dora indicator (up to num_dora).
    Returns the tile_ids of the ura dora indicator tiles.
    """
    ura_dora = []
    for i in range(num_dora):
        index = FIRST_URA_DORA_INDEX + i
        if index < len(round_state.dead_wall):
            ura_dora.append(round_state.dead_wall[index])
    return ura_dora
