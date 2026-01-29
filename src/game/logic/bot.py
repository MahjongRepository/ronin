"""
Bot decision making for mahjong game.

Provides AI logic for bot players to make decisions during gameplay.
The tsumogiri bot strategy focuses on keeping hands closed for riichi play.
"""

from enum import Enum
from typing import TYPE_CHECKING

from mahjong.shanten import Shanten

from game.logic.enums import KanType, PlayerAction
from game.logic.melds import can_call_pon
from game.logic.riichi import can_declare_riichi
from game.logic.tiles import HONOR_34_START, hand_to_34_array, tile_to_34
from game.logic.types import BotAction
from game.logic.win import can_call_ron, can_declare_tsumo

if TYPE_CHECKING:
    from game.logic.state import MahjongPlayer, MahjongRoundState


class BotStrategy(Enum):
    """Available bot strategies."""

    TSUMOGIRI = "tsumogiri"  # tsumogiri: always call wins, never call melds, discard last drawn tile


class BotPlayer:
    """
    Bot player with configurable decision-making strategy.
    """

    def __init__(self, strategy: BotStrategy = BotStrategy.TSUMOGIRI) -> None:
        self.strategy = strategy


def should_call_pon(
    bot: BotPlayer,
    player: MahjongPlayer,
    discarded_tile: int,
    round_state: MahjongRoundState,  # noqa: ARG001
) -> bool:
    """
    Decide whether bot should call pon on a discarded tile.

    For tsumogiri bot: always return False to keep hand closed for riichi.
    """
    if bot.strategy == BotStrategy.TSUMOGIRI:
        return False

    # validate the call is possible
    return can_call_pon(player, discarded_tile)


def should_call_chi(
    bot: BotPlayer,
    player: MahjongPlayer,  # noqa: ARG001
    discarded_tile: int,  # noqa: ARG001
    chi_options: list[tuple[int, int]],
    round_state: MahjongRoundState,  # noqa: ARG001
) -> tuple[int, int] | None:
    """
    Decide whether bot should call chi on a discarded tile.

    For tsumogiri bot: always return None to keep hand closed for riichi.

    Returns the chosen chi combination (two tiles from hand) or None to pass.
    """
    if bot.strategy == BotStrategy.TSUMOGIRI:
        return None

    # validate options exist
    if not chi_options:
        return None

    return chi_options[0]


def should_call_kan(
    bot: BotPlayer,
    player: MahjongPlayer,  # noqa: ARG001
    kan_type: KanType,  # noqa: ARG001
    tile_34: int,  # noqa: ARG001
    round_state: MahjongRoundState,  # noqa: ARG001
) -> bool:
    """
    Decide whether bot should call kan (open, closed, or added).

    For tsumogiri bot: always return False.
    Open/added kan opens the hand; closed kan reveals tiles.
    """
    return bot.strategy != BotStrategy.TSUMOGIRI


def should_call_ron(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,
    discarded_tile: int,
    round_state: MahjongRoundState,
) -> bool:
    """
    Decide whether bot should call ron (win on discard).

    All strategies: always call ron if possible.
    """
    return can_call_ron(player, discarded_tile, round_state)


def should_call_riichi(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Decide whether bot should declare riichi.

    All strategies: always call riichi if possible.
    """
    return can_declare_riichi(player, round_state)


def should_declare_tsumo(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Decide whether bot should declare tsumo (self-draw win).

    All strategies: always call tsumo if possible.
    """
    return can_declare_tsumo(player, round_state)


def select_discard(
    bot: BotPlayer,
    player: MahjongPlayer,
    round_state: MahjongRoundState,  # noqa: ARG001
) -> int:
    """
    Select a tile to discard from the player's hand.

    For tsumogiri bot: always discard the last drawn tile.
    For smarter bot: use shanten-based discard to improve hand.
    """
    if not player.tiles:
        raise ValueError("cannot select discard from empty hand")

    if bot.strategy == BotStrategy.TSUMOGIRI:
        # tsumogiri: discard the last tile (most recently drawn)
        return player.tiles[-1]

    # shanten-based discard: find the tile that minimizes shanten
    return _select_best_discard(player)


def select_riichi_discard(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,
) -> int:
    """
    Select a tile to discard when declaring riichi.

    Finds a tile that keeps the hand in tempai after discard.
    """
    if not player.tiles:
        raise ValueError("cannot select riichi discard from empty hand")

    # find tiles that keep hand in tempai
    valid_discards = _find_tempai_discards(player)

    if not valid_discards:
        # fallback to last tile if no valid tempai discard found
        return player.tiles[-1]

    # prefer discarding the last drawn tile if it keeps tempai
    last_tile = player.tiles[-1]
    if last_tile in valid_discards:
        return last_tile

    # otherwise return first valid discard
    return valid_discards[0]


def get_bot_action(
    bot: BotPlayer,
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> BotAction:
    """
    Determine the bot's action during their turn.

    Checks available actions in priority order and returns the chosen action.
    """
    # check for tsumo win first (highest priority)
    if should_declare_tsumo(bot, player, round_state):
        return BotAction(action=PlayerAction.TSUMO)

    # check for riichi
    if should_call_riichi(bot, player, round_state):
        discard_tile = select_riichi_discard(bot, player)
        return BotAction(action=PlayerAction.RIICHI, tile_id=discard_tile)

    # default: discard a tile
    discard_tile = select_discard(bot, player, round_state)
    return BotAction(action=PlayerAction.DISCARD, tile_id=discard_tile)


def _select_best_discard(player: MahjongPlayer) -> int:
    """
    Select the best tile to discard based on shanten calculation.

    Tries each tile and picks one that results in lowest shanten
    (or maintains current shanten with best ukeire).
    """
    shanten = Shanten()
    tiles_34 = hand_to_34_array(player.tiles)
    current_shanten = shanten.calculate_shanten(tiles_34)

    best_tile = player.tiles[-1]  # default to tsumogiri
    best_shanten = current_shanten + 1  # worse than current

    for tile_id in player.tiles:
        tile_34 = tile_to_34(tile_id)

        # simulate discard
        tiles_34[tile_34] -= 1
        new_shanten = shanten.calculate_shanten(tiles_34)
        tiles_34[tile_34] += 1  # restore

        # prefer lower shanten
        if new_shanten < best_shanten:
            best_shanten = new_shanten
            best_tile = tile_id
        elif new_shanten == best_shanten:
            # tie-breaker: prefer discarding isolated honor tiles or terminals
            if _is_isolated_tile(tile_34, tiles_34) and not _is_isolated_tile(
                tile_to_34(best_tile), tiles_34
            ):
                best_tile = tile_id

    return best_tile


def _find_tempai_discards(player: MahjongPlayer) -> list[int]:
    """
    Find all tiles that can be discarded while maintaining tempai.

    Returns a list of tile_ids that keep the hand in tempai after discard.
    """
    shanten = Shanten()
    valid_discards = []

    for tile_id in player.tiles:
        # only remove one instance of the tile
        remaining = list(player.tiles)
        remaining.remove(tile_id)

        tiles_34 = hand_to_34_array(remaining)
        new_shanten = shanten.calculate_shanten(tiles_34)

        # tempai = shanten 0
        if new_shanten == 0:
            valid_discards.append(tile_id)

    return valid_discards


def _is_isolated_tile(tile_34: int, tiles_34: list[int]) -> bool:
    """
    Check if a tile is isolated (no adjacent tiles for sequences).

    Isolated tiles are good discard candidates as they don't contribute to melds.
    Honor tiles (27-33) are always "isolated" in terms of sequences.
    """
    # honor tiles can't form sequences
    if tile_34 >= HONOR_34_START:
        return True

    # check suit and position
    suit_start = (tile_34 // 9) * 9

    # check for adjacent tiles (for sequence potential)
    has_adjacent = False

    # check tile-1 (if not at suit boundary)
    if tile_34 > suit_start and tiles_34[tile_34 - 1] > 0:
        has_adjacent = True

    # check tile+1 (if not at suit boundary)
    if tile_34 < suit_start + 8 and tiles_34[tile_34 + 1] > 0:
        has_adjacent = True

    # check tile-2 (for potential 2-gap sequences)
    if tile_34 > suit_start + 1 and tiles_34[tile_34 - 2] > 0:
        has_adjacent = True

    # check tile+2
    if tile_34 < suit_start + 7 and tiles_34[tile_34 + 2] > 0:
        has_adjacent = True

    return not has_adjacent
