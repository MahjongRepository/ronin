from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.enums import AbortiveDrawType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import WINDS_34, is_terminal_or_honor, tile_to_34
from game.logic.types import AbortiveDrawResult

if TYPE_CHECKING:
    from game.logic.settings import GameSettings
    from game.logic.state import (
        MahjongPlayer,
        MahjongRoundState,
    )
    from game.logic.types import RobbedKan


def can_call_kyuushu_kyuuhai(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    *,
    settings: GameSettings,
) -> bool:
    """
    Check if a player can declare kyuushu kyuuhai (nine terminals abortive draw).

    Requirements:
    - Kyuushu kyuuhai is enabled in the settings
    - The player's first draw, uninterrupted: they have not discarded yet and no player has made any call (closed
      kans included)
    - Hand contains at least kyuushu_min_types different terminal/honor tile types
    """
    if not settings.has_kyuushu_kyuuhai:
        return False

    if player.discards:
        return False

    if round_state.has_any_call():
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


def check_four_riichi(round_state: MahjongRoundState) -> bool:
    """
    Check if all players have declared riichi (abortive draw condition).
    """
    riichi_count = sum(1 for p in round_state.players if p.is_riichi)
    return riichi_count == NUM_PLAYERS


def check_four_kans(round_state: MahjongRoundState, settings: GameSettings) -> bool:
    """
    Check if four kans have been declared by different players (abortive draw condition).

    The round ends when 4 kans are declared by 2+ different players, once the fourth kan's replacement discard passes
    without a ron. If one player has all 4 kans, the game continues (suukantsu possible).
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


def find_passed_discard_abort(round_state: MahjongRoundState, settings: GameSettings) -> AbortiveDrawType | None:
    """
    Return the abortive draw that ends the round once the current discard passes every ron, or None.

    Four riichi applies once the fourth riichi has taken effect, four kans to the fourth kan's replacement discard.
    """
    if settings.has_suucha_riichi and check_four_riichi(round_state):
        return AbortiveDrawType.FOUR_RIICHI

    if settings.has_suukaikan and check_four_kans(round_state, settings):
        return AbortiveDrawType.FOUR_KANS

    return None


def check_four_winds(round_state: MahjongRoundState, settings: GameSettings) -> bool:
    """
    Check if the first 4 discards are all the same wind tile (abortive draw condition).

    Requirements:
    - Exactly 4 discards have been made (check len(all_discards) == 4)
    - All 4 discards are the same wind tile (E, S, W, or N)
    - No open melds have been called (closed kans do not count)
    """
    # check exactly N discards (one per player)
    if len(round_state.all_discards) != settings.four_winds_discard_count:
        return False

    # check no open melds
    if any(p.has_open_melds() for p in round_state.players):
        return False

    # convert discards to 34-format
    discard_34s = [tile_to_34(t) for t in round_state.all_discards]

    # check all same and all are wind tiles
    first_tile = discard_34s[0]
    if first_tile not in WINDS_34:
        return False

    return all(t == first_tile for t in discard_34s)


def process_abortive_draw(
    round_state: MahjongRoundState,
    draw_type: AbortiveDrawType,
    *,
    ron_seats: list[int] | None = None,
    robbed_kan: RobbedKan | None = None,
) -> AbortiveDrawResult:
    """
    Process an abortive draw.

    No score changes occur. Honba increment is handled by process_round_end. ron_seats names the declarers of a triple
    ron, and robbed_kan the kan they robbed when it was a chankan.
    """
    scores = {p.seat: p.score for p in round_state.players}
    return AbortiveDrawResult(
        reason=draw_type,
        scores=scores,
        score_changes={p.seat: 0 for p in round_state.players},
        ron_seats=ron_seats,
        robbed_kan=robbed_kan,
    )
