"""
Tile representation utilities for Mahjong game.
"""

from random import randint, seed

# tile ranges in 136-format (4 copies of each tile)
# man (characters): 0-35 (1m-9m, 4 copies each)
# pin (circles): 36-71 (1p-9p, 4 copies each)
# sou (bamboo): 72-107 (1s-9s, 4 copies each)
# honors: 108-135 (E, S, W, N, Haku, Hatsu, Chun, 4 copies each)

MAN_START = 0
MAN_END = 35
PIN_START = 36
PIN_END = 71
SOU_START = 72
SOU_END = 107
HONOR_START = 108
HONOR_END = 135

# tile ranges in 34-format (each unique tile type)
MAN_34_START = 0
MAN_34_END = 8
PIN_34_START = 9
PIN_34_END = 17
SOU_34_START = 18
SOU_34_END = 26
HONOR_34_START = 27
HONOR_34_END = 33

# honor tile indices in 34-format
EAST_34 = 27
SOUTH_34 = 28
WEST_34 = 29
NORTH_34 = 30
HAKU_34 = 31  # white dragon
HATSU_34 = 32  # green dragon
CHUN_34 = 33  # red dragon

# wind tiles in 34-format
WINDS_34 = [EAST_34, SOUTH_34, WEST_34, NORTH_34]

# dragon tiles in 34-format
DRAGONS_34 = [HAKU_34, HATSU_34, CHUN_34]

# terminal tiles in 34-format (1 and 9 of each suit)
TERMINALS_34 = [0, 8, 9, 17, 18, 26]


def tile_to_34(tile_id: int) -> int:
    """
    Convert 136-format tile ID to 34-format.

    In 136-format, each tile type has 4 copies (tile_id // 4 gives the type).
    In 34-format, each tile type is represented by a single index (0-33).
    """
    return tile_id // 4


def is_terminal(tile_34: int) -> bool:
    """
    Check if tile is a terminal (1 or 9 of any suit).
    """
    return tile_34 in TERMINALS_34


def is_honor(tile_34: int) -> bool:
    """
    Check if tile is an honor (wind or dragon).
    """
    return HONOR_34_START <= tile_34 <= HONOR_34_END


def is_terminal_or_honor(tile_34: int) -> bool:
    """
    Check if tile is terminal or honor (yaochuuhai).
    """
    return is_terminal(tile_34) or is_honor(tile_34)


def generate_wall(seed_value: float, round_number: int) -> list[int]:
    """
    Generate and shuffle a wall of 136 tiles.

    Uses seed + round_number to ensure reproducible but unique walls per round.
    """
    wall_seed = seed_value + round_number
    seed(wall_seed)

    wall = list(range(136))
    _randomly_shuffle_array(wall)
    _randomly_shuffle_array(wall)

    return wall


def _randomly_shuffle_array(array: list) -> None:
    """
    Shuffle array in-place.
    """
    rand_seeds = [randint(0, len(array) - 1) for _ in range(len(array))]  # noqa: S311
    for x in range(len(array)):
        src = x
        dst = rand_seeds[x]
        array[src], array[dst] = array[dst], array[src]


def sort_tiles(tiles: list[int]) -> list[int]:
    """
    Sort tiles by their 34-format value, preserving order within same type.
    """
    return sorted(tiles)


def hand_to_34_array(tiles: list[int] | tuple[int, ...]) -> list[int]:
    """
    Convert a list of 136-format tile IDs to a 34-array (tile counts).

    The 34-array has 34 elements, where each index represents a tile type
    and the value is the count of that tile type in the hand.
    """
    tiles_34 = [0] * 34
    for tile_id in tiles:
        tile_index = tile_to_34(tile_id)
        tiles_34[tile_index] += 1
    return tiles_34
