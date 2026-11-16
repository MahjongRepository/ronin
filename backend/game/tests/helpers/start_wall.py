from __future__ import annotations

from typing import TYPE_CHECKING

from game.engine import NUM_PLAYERS, NUM_TILES

if TYPE_CHECKING:
    from collections.abc import Sequence

TILES_PER_DEAL_BLOCK = 4
DEAL_BLOCKS = 3
DEAD_WALL_STACKS = 7
DEAD_WALL_SIZE = 2 * DEAD_WALL_STACKS
RINSHAN_STACKS = 2
MAX_RINSHAN_DRAWS = 2 * RINSHAN_STACKS
MAX_DORA_INDICATORS = DEAD_WALL_STACKS - RINSHAN_STACKS

FIRST_DORA_POSITION = RINSHAN_STACKS
URA_OFFSET = DEAD_WALL_STACKS
FIRST_URA_POSITION = FIRST_DORA_POSITION + URA_OFFSET
DEAL_ROUND_SIZE = TILES_PER_DEAL_BLOCK * NUM_PLAYERS
FINAL_DEAL_START = DEAL_BLOCKS * DEAL_ROUND_SIZE
FIRST_DRAW_POSITION = FINAL_DEAL_START + NUM_PLAYERS
DEAD_WALL_START = NUM_TILES - DEAD_WALL_SIZE
RINSHAN_POSITIONS = tuple(
    DEAD_WALL_START + stack + layer for stack in range(RINSHAN_STACKS) for layer in (0, URA_OFFSET)
)


def _deal_positions(seat: int) -> list[int]:
    blocks = [
        position
        for block in range(DEAL_BLOCKS)
        for position in range(
            block * DEAL_ROUND_SIZE + seat * TILES_PER_DEAL_BLOCK,
            block * DEAL_ROUND_SIZE + (seat + 1) * TILES_PER_DEAL_BLOCK,
        )
    ]
    return [*blocks, FINAL_DEAL_START + seat]


def make_start_wall(
    hands: Sequence[Sequence[int]],
    *,
    draws: Sequence[int] = (),
    rinshan: Sequence[int] = (),
    ura: Sequence[int] = (),
) -> tuple[int, ...]:
    """
    Build a full 136-tile wall for new_game that deals each seat its 13-tile hand and then the live draws in order.

    The layout is the setup input's, not any engine's internals: the deal in blocks of four then one per seat, the live
    draws after it, and the 14-tile dead wall at the end as seven two-tile stacks (tops, then bottoms), the two nearest
    the break holding the rinshan tiles. hands are by seat with the first dealer at seat 0, and draws are the live
    wall's first draws (the dealer's first); rinshan are the kan replacement tiles in draw order and ura the ura dora
    indicators in reveal order. Every other position holds the remaining tiles in ascending order.
    """
    if FIRST_DRAW_POSITION + len(draws) > DEAD_WALL_START:
        raise ValueError(f"{len(draws)} draws spill past the live wall into the dead wall")

    if len(rinshan) > MAX_RINSHAN_DRAWS:
        raise ValueError(f"the dead wall holds {MAX_RINSHAN_DRAWS} rinshan tiles, got {len(rinshan)}")

    if len(ura) > MAX_DORA_INDICATORS:
        raise ValueError(f"the dead wall holds {MAX_DORA_INDICATORS} ura dora indicators, got {len(ura)}")

    placed = {
        position: tile
        for seat, hand in enumerate(hands)
        for position, tile in zip(_deal_positions(seat), hand, strict=True)
    }
    placed.update(enumerate(draws, start=FIRST_DRAW_POSITION))
    placed.update(zip(RINSHAN_POSITIONS, rinshan, strict=False))
    placed.update(enumerate(ura, start=DEAD_WALL_START + FIRST_URA_POSITION))
    if len(set(placed.values())) != len(placed):
        raise ValueError(f"start wall repeats a tile: {sorted(placed.values())}")

    rest = iter(tile for tile in range(NUM_TILES) if tile not in placed.values())
    return tuple(placed[position] if position in placed else next(rest) for position in range(NUM_TILES))
