"""
Abortive draw conditions for Mahjong.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.enums import AbortiveDrawType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.tiles import WINDS_34, is_terminal_or_honor, tile_to_34
from game.logic.types import AbortiveDrawResult

if TYPE_CHECKING:
    from game.logic.settings import GameSettings
    from game.logic.state import (
        MahjongGameState,
        MahjongPlayer,
        MahjongRoundState,
    )


def can_call_kyuushu_kyuuhai(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> bool:
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

    # check if any calls have been made (including closed kans)
    if round_state.players_with_open_hands:
        return False
    if any(p.melds for p in round_state.players):
        return False

    # count unique terminal/honor tile types in hand
    terminal_honor_types = _count_terminal_honor_types(player.tiles)

    return terminal_honor_types >= settings.kyuushu_min_types


def _count_terminal_honor_types(tiles: list[int] | tuple[int, ...]) -> int:
    """
    Count the number of different terminal/honor tile types in a hand.
    """
    unique_types = set()
    for tile_id in tiles:
        tile_34 = tile_to_34(tile_id)
        if is_terminal_or_honor(tile_34):
            unique_types.add(tile_34)
    return len(unique_types)


def call_kyuushu_kyuuhai(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, AbortiveDrawResult]:
    """
    Execute kyuushu kyuuhai abortive draw.

    Returns (unchanged_round_state, result).
    The round_state is not modified by this function - phase change is done by caller.
    """
    scores = {p.seat: p.score for p in round_state.players}
    result = AbortiveDrawResult(
        reason=AbortiveDrawType.NINE_TERMINALS,
        scores=scores,
        score_changes={p.seat: 0 for p in round_state.players},
        seat=round_state.current_player_seat,
    )
    return round_state, result


def check_four_riichi(round_state: MahjongRoundState, settings: GameSettings) -> bool:
    """
    Check if all players have declared riichi (abortive draw condition).
    """
    riichi_count = sum(1 for p in round_state.players if p.is_riichi)
    return riichi_count == settings.num_players


def check_triple_ron(ron_callers: list[int], triple_ron_count: int) -> bool:
    """
    Check if enough players simultaneously declare ron for an abortive draw.

    When 2 players can ron, both win (double ron).
    When 3 players can ron, it's an abortive draw (triple ron).
    """
    return len(ron_callers) == triple_ron_count


def check_four_kans(round_state: MahjongRoundState, settings: GameSettings) -> bool:
    """
    Check if four kans have been declared by different players.

    This is an abortive draw condition - if 4 kans are declared by 2+ different players,
    the round ends. If one player has all 4 kans, the game continues (suukantsu possible).
    """
    total_kans = 0
    players_with_kans = set()

    for player in round_state.players:
        player_kans = sum(1 for m in player.melds if m.type in (FrozenMeld.KAN, FrozenMeld.SHOUMINKAN))
        total_kans += player_kans
        if player_kans > 0:
            players_with_kans.add(player.seat)

    # abortive draw only if max kans reached AND multiple players have kans
    return total_kans >= settings.max_kans_per_round and len(players_with_kans) >= settings.min_players_for_kan_abort


def check_four_winds(round_state: MahjongRoundState, settings: GameSettings) -> bool:
    """
    Check if the first 4 discards are all the same wind tile (abortive draw condition).

    Requirements:
    - Exactly 4 discards have been made (check len(all_discards) == 4)
    - All 4 discards are the same wind tile (E, S, W, or N)
    - No open melds have been called (players_with_open_hands is empty)
    """
    # check exactly N discards (one per player)
    if len(round_state.all_discards) != settings.four_winds_discard_count:
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


def process_abortive_draw(
    game_state: MahjongGameState,
    draw_type: AbortiveDrawType,
) -> AbortiveDrawResult:
    """
    Process an abortive draw.

    No score changes occur. Honba increment is handled by process_round_end.
    """
    scores = {p.seat: p.score for p in game_state.round_state.players}
    return AbortiveDrawResult(
        reason=draw_type,
        scores=scores,
        score_changes={p.seat: 0 for p in game_state.round_state.players},
    )
