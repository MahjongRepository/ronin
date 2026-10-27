from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES
from game.logic.wall import (
    DEAD_WALL_SIZE,
    DEAD_WALL_STACKS,
    DEAL_BLOCKS,
    MAX_DORA_INDICATORS,
    MAX_RINSHAN_DRAWS,
    RINSHAN_STACKS,
    TILES_PER_DEAL_BLOCK,
    DeadWall,
    TileStack,
    Wall,
    build_dead_wall,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

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


def make_dead_wall(
    tiles: Sequence[int | None] | None = None,
    *,
    dora_indicators: Sequence[int] = (),
    reserved: Iterable[int] = (),
    pending_dora_count: int = 0,
) -> DeadWall:
    """
    Build a dead wall for a test from 14 slots laid out as tops (0-6) then bottoms (7-13), with stack 0 at the break.

    A None slot (or no tiles at all) is filled with the highest tile ids not in reserved; dora_indicators go on the
    indicator tops in order and count as revealed (at least one is). A slot that repeats another, or a specified top
    that disagrees with dora_indicators, is a mistake in the test and raises.
    """
    layout: list[int | None] = list(tiles) if tiles is not None else [None] * DEAD_WALL_SIZE
    if len(layout) != DEAD_WALL_SIZE:
        raise ValueError(f"dead wall needs {DEAD_WALL_SIZE} slots, got {len(layout)}")

    for i, indicator in enumerate(dora_indicators):
        position = FIRST_DORA_POSITION + i
        if layout[position] not in (None, indicator):
            raise ValueError(
                f"dora indicator {i} is {indicator} but dead wall slot {position} holds {layout[position]}"
            )

        layout[position] = indicator

    specified = [t for t in layout if t is not None]
    if len(set(specified)) != len(specified):
        raise ValueError(f"dead wall repeats a tile: {sorted(specified)}")

    excluded = set(reserved) | set(specified)
    filler = iter(t for t in range(NUM_TILES - 1, -1, -1) if t not in excluded)
    filled = [t if t is not None else next(filler) for t in layout]
    stacks = [TileStack(top=filled[i], bottom=filled[i + URA_OFFSET]) for i in range(DEAD_WALL_STACKS)]
    base = build_dead_wall(stacks)
    return DeadWall(
        rinshan=base.rinshan,
        indicators=base.indicators,
        reserve=base.reserve,
        revealed_count=max(1, len(dora_indicators)),
        pending_reveals=pending_dora_count,
    )


def make_wall(
    *,
    live_tiles: Sequence[int] = (),
    dead_wall: Sequence[int | None] | None = None,
    dora_indicators: Sequence[int] = (),
    reserved: Iterable[int] = (),
    pending_dora_count: int = 0,
    dice: tuple[int, int] = (1, 1),
) -> Wall:
    """
    Build a test wall; the dead wall filler avoids live_tiles and reserved (hand, meld and discard tiles).

    A live tile the test also placed in the dead wall (a dora indicator inside a range of live tiles) is swapped for a
    free tile in the same position, so the wall stays a valid partition with the live count the test asked for.
    """
    dead = make_dead_wall(
        dead_wall,
        dora_indicators=dora_indicators,
        reserved=(*reserved, *live_tiles),
        pending_dora_count=pending_dora_count,
    )
    dead_tiles = set(dead.tiles)
    taken = dead_tiles | set(reserved) | set(live_tiles)
    free = iter(t for t in range(NUM_TILES - 1, -1, -1) if t not in taken)
    live = tuple(next(free) if t in dead_tiles else t for t in live_tiles)
    return Wall(live_tiles=live, dead_wall=dead, dice=dice)


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
    Build a full 136-tile wall for start_game that deals each seat its 13-tile hand and then the live draws in order.

    hands are by seat with the first dealer at seat 0, and draws are the live wall's first draws (the dealer's first);
    rinshan are the kan replacement tiles in draw order and ura the ura dora indicators in reveal order. Every other
    position holds the remaining tiles in ascending order.
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
