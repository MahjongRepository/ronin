from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from xiangting import PlayerCount, calculate_necessary_tiles, calculate_replacement_number, calculate_unnecessary_tiles

if TYPE_CHECKING:
    from game.logic.meld_wrapper import FrozenMeld

logger = structlog.get_logger()

AGARI_STATE: int = -1

MAX_TILE_COPIES = 4

# Xiangting requires tile count to be 3n+1 or 3n+2.
# Other counts (empty hands, test fixtures with unusual sizes) can't be tenpai.
_NOT_TENPAI: int = 8


def calculate_shanten(tiles_34: list[int]) -> int:
    """
    Calculate the minimum shanten number across all hand patterns (regular, chiitoitsu, kokushi).

    Used by the backend scripts; the engine judges waits and tenpai with the mask functions below.
    """
    total = sum(tiles_34)
    if total == 0 or total % 3 not in (1, 2):
        if total > 0:
            logger.warning("unexpected tile count in shanten calculation", tile_count=total)

        return _NOT_TENPAI

    return calculate_replacement_number(tiles_34, PlayerCount.FOUR) - 1


def closed_waits_mask(closed_34: list[int]) -> int:
    """
    Return the tile types that complete a waiting closed part (3n+1 tiles) as a bitmask over the 34 types.

    Covers regular, chiitoitsu and kokushi shapes. Judges the closed part alone: a type held 4 times in it is never a
    wait, but copies in melds are not seen (see held_out_mask). A closed part that is not tenpai has no waits.
    """
    replacement_number, necessary = calculate_necessary_tiles(closed_34, PlayerCount.FOUR)
    return necessary if replacement_number == 1 else 0


def is_complete_closed(closed_34: list[int]) -> bool:
    """
    Return whether a drawn closed part (3n+2 tiles) is complete: n sets and a pair, chiitoitsu or kokushi.

    Judges the closed part alone, which decides a hand's shape since melds are complete sets.
    """
    return calculate_replacement_number(closed_34, PlayerCount.FOUR) == 0


def held_out_mask(closed_34: list[int], melds: tuple[FrozenMeld, ...] | list[FrozenMeld]) -> int:
    """
    Return the tile types whose 4 copies are all in the closed part plus the player's own melds, as a bitmask.

    Such a type cannot be waited on (karaten); copies in other players' rivers or melds never count.
    """
    counts = list(closed_34)
    for meld in melds:
        for tile_id in meld.tiles:
            counts[tile_id // 4] += 1

    mask = 0
    for tile_34, count in enumerate(counts):
        if count >= MAX_TILE_COPIES:
            mask |= 1 << tile_34

    return mask


def waits_mask(closed_34: list[int], melds: tuple[FrozenMeld, ...] | list[FrozenMeld]) -> int:
    """
    Return the waits of a waiting closed part (3n+1 tiles) with its melds, as a bitmask, karaten types excluded.

    An empty mask means the hand is not tenpai under our karaten rule.
    """
    waits = closed_waits_mask(closed_34)
    if not waits:
        return 0

    return waits & ~held_out_mask(closed_34, melds)


def tenpai_discards_mask(drawn_34: list[int], melds: tuple[FrozenMeld, ...] | list[FrozenMeld]) -> int:
    """
    Return the tile types whose discard leaves a drawn closed part (3n+2 tiles) tenpai, as a bitmask.

    A complete hand keeps tenpai on any discard, since it then waits on the discarded type. The karaten filter runs per
    candidate only when melds or a closed quad can hold all copies of a wait.
    """
    replacement_number, candidates = calculate_unnecessary_tiles(drawn_34, PlayerCount.FOUR)
    if replacement_number > 1:
        return 0

    if replacement_number == 0:
        candidates = 0
        for tile_34, count in enumerate(drawn_34):
            if count:
                candidates |= 1 << tile_34

    if not melds and max(drawn_34) < MAX_TILE_COPIES:
        return candidates

    counts = list(drawn_34)
    kept = 0
    remaining = candidates
    while remaining:
        bit = remaining & -remaining
        tile_34 = bit.bit_length() - 1
        counts[tile_34] -= 1
        if waits_mask(counts, melds):
            kept |= bit

        counts[tile_34] += 1
        remaining ^= bit

    return kept


def mask_to_tile_types(mask: int) -> set[int]:
    """
    Return the tile types (0-33) set in a 34-type bitmask.
    """
    tile_types = set()
    while mask:
        bit = mask & -mask
        tile_types.add(bit.bit_length() - 1)
        mask ^= bit

    return tile_types
