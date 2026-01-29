"""
Abortive draw conditions for Mahjong.
"""

from typing import TYPE_CHECKING

from mahjong.meld import Meld

from game.logic.enums import AbortiveDrawType
from game.logic.tiles import WINDS_34, is_terminal_or_honor, tile_to_34
from game.logic.types import AbortiveDrawResult

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState


# minimum number of different terminal/honor tile types for kyuushu kyuuhai
KYUUSHU_MIN_TYPES = 9

# game constants
NUM_PLAYERS = 4
TRIPLE_RON_COUNT = 3
MIN_PLAYERS_FOR_KAN_ABORT = 2
FOUR_WINDS_DISCARD_COUNT = 4


def can_call_kyuushu_kyuuhai(player: MahjongPlayer, round_state: MahjongRoundState) -> bool:
    """
    Check if a player can declare kyuushu kyuuhai (nine terminals abortive draw).

    Requirements:
    - Player's first draw (no discards from any player, no melds)
    - Hand contains 9 or more different terminal/honor tile types
    """
    # check if any discards have been made
    for p in round_state.players:
        if p.discards:
            return False

    # check if any melds have been made
    if round_state.players_with_open_hands:
        return False

    # count unique terminal/honor tile types in hand
    terminal_honor_types = _count_terminal_honor_types(player.tiles)

    return terminal_honor_types >= KYUUSHU_MIN_TYPES


def _count_terminal_honor_types(tiles: list[int]) -> int:
    """
    Count the number of different terminal/honor tile types in a hand.
    """
    unique_types = set()
    for tile_id in tiles:
        tile_34 = tile_to_34(tile_id)
        if is_terminal_or_honor(tile_34):
            unique_types.add(tile_34)
    return len(unique_types)


def call_kyuushu_kyuuhai(round_state: MahjongRoundState) -> AbortiveDrawResult:
    """
    Execute kyuushu kyuuhai abortive draw.
    """
    return AbortiveDrawResult(
        reason=AbortiveDrawType.NINE_TERMINALS,
        seat=round_state.current_player_seat,
    )


def check_four_riichi(round_state: MahjongRoundState) -> bool:
    """
    Check if all 4 players have declared riichi (abortive draw condition).
    """
    riichi_count = sum(1 for p in round_state.players if p.is_riichi)
    return riichi_count == NUM_PLAYERS


def check_triple_ron(ron_callers: list[int]) -> bool:
    """
    Check if 3 players simultaneously declare ron (abortive draw condition).

    When 2 players can ron, both win (double ron).
    When 3 players can ron, it's an abortive draw (triple ron).
    """
    return len(ron_callers) == TRIPLE_RON_COUNT


def check_four_kans(round_state: MahjongRoundState) -> bool:
    """
    Check if four kans have been declared by different players.

    This is an abortive draw condition - if 4 kans are declared by 2+ different players,
    the round ends. If one player has all 4 kans, the game continues (suukantsu possible).
    """
    total_kans = 0
    players_with_kans = set()

    for player in round_state.players:
        player_kans = sum(1 for m in player.melds if m.type in (Meld.KAN, Meld.SHOUMINKAN))
        total_kans += player_kans
        if player_kans > 0:
            players_with_kans.add(player.seat)

    # abortive draw only if 4 kans AND multiple players have kans
    return total_kans >= NUM_PLAYERS and len(players_with_kans) >= MIN_PLAYERS_FOR_KAN_ABORT


def check_four_winds(round_state: MahjongRoundState) -> bool:
    """
    Check if the first 4 discards are all the same wind tile (abortive draw condition).

    Requirements:
    - Exactly 4 discards have been made (check len(all_discards) == 4)
    - All 4 discards are the same wind tile (E, S, W, or N)
    - No open melds have been called (players_with_open_hands is empty)
    """
    # check exactly 4 discards
    if len(round_state.all_discards) != FOUR_WINDS_DISCARD_COUNT:
        return False

    # check no open melds
    if round_state.players_with_open_hands:
        return False

    # convert discards to 34-format
    discard_34s = [tile_to_34(t) for t in round_state.all_discards]

    # check all same and all are wind tiles
    first_tile = discard_34s[0]
    if first_tile not in WINDS_34:
        return False

    return all(t == first_tile for t in discard_34s)


def process_abortive_draw(game_state: MahjongGameState, draw_type: AbortiveDrawType) -> AbortiveDrawResult:
    """
    Process an abortive draw.

    No score changes occur. Honba increment is handled by process_round_end.
    """
    return AbortiveDrawResult(
        reason=draw_type,
        score_changes={p.seat: 0 for p in game_state.round_state.players},
    )
