"""
Wall state and operations for Mahjong.

The Wall encapsulates all tile wall mechanics: the live wall for drawing,
the dead wall for replacement draws and dora indicators, and dora management.

Dead wall layout (14 tiles as 7 stacks of 2):
  top row:    [0] [1] [2] [3] [4] [5] [6]
  bottom row: [7] [8] [9] [10] [11] [12] [13]

  Dora indicators: top row indices 2, 3, 4, 5, 6
  Ura dora: bottom row indices 7, 8, 9, 10, 11
  Replacement draws: from index 13 (end) via pop()
"""

from pydantic import BaseModel, ConfigDict

from game.logic.exceptions import InvalidActionError
from game.logic.rng import TOTAL_WALL_SIZE, generate_shuffled_wall_and_dice
from game.logic.tiles import sort_tiles

DEAD_WALL_SIZE = 14
FIRST_DORA_INDEX = 2
MAX_DORA_INDICATORS = 5
URA_DORA_START_INDEX = 7
NUM_PLAYERS = 4
TILES_PER_DEAL_BLOCK = 4
DEAL_BLOCKS = 3
TILES_PER_FINAL_DEAL = 1

# Wall ring constants for dice-based wall breaking
STACKS_PER_PLAYER = 17  # 34 tiles / 2 tiles per stack
TILES_PER_STACK = 2
TOTAL_STACKS = NUM_PLAYERS * STACKS_PER_PLAYER  # 68
DEAD_WALL_STACKS = DEAD_WALL_SIZE // TILES_PER_STACK  # 7
LIVE_WALL_STACKS = TOTAL_STACKS - DEAD_WALL_STACKS  # 61


class WallBreakInfo(BaseModel):
    """Computed wall break position from dice roll."""

    model_config = ConfigDict(frozen=True)

    dice_sum: int  # Sum of two dice (2-12)
    target_seat: int  # Seat whose wall is broken (0-3)
    break_stack: int  # First dead wall stack index in the 68-stack ring (0-67)


class Wall(BaseModel):
    """Immutable wall state for a mahjong round."""

    model_config = ConfigDict(frozen=True)

    live_tiles: tuple[int, ...] = ()
    dead_wall_tiles: tuple[int, ...] = ()
    dora_indicators: tuple[int, ...] = ()
    pending_dora_count: int = 0
    dice: tuple[int, int] = (1, 1)  # Two dice values (each 1-6), default (1,1) for tests


def compute_wall_break_info(dice: tuple[int, int], dealer_seat: int) -> WallBreakInfo:
    """
    Compute wall break position from dice roll and dealer seat.

    Target seat: count counter-clockwise from dealer by (dice_sum - 1).
    Break stack: count dice_sum stacks from the right end of the target
    player's wall segment. The 7 stacks starting at break_stack (going
    right, wrapping) form the dead wall.
    """
    dice_sum = dice[0] + dice[1]
    target_seat = (dealer_seat + dice_sum - 1) % NUM_PLAYERS
    break_stack = ((target_seat + 1) * STACKS_PER_PLAYER - dice_sum) % TOTAL_STACKS
    return WallBreakInfo(
        dice_sum=dice_sum,
        target_seat=target_seat,
        break_stack=break_stack,
    )


def _split_wall_by_dice(
    tiles: list[int], dice: tuple[int, int], dealer_seat: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """
    Split 136 shuffled tiles into live wall and dead wall based on dice break position.

    The tiles list represents 68 stacks of 2 in a ring. The dice determine where
    to break the ring: 7 stacks to the right of the break form the dead wall,
    the remaining 61 stacks to the left form the live wall.

    Returns (live_tiles, dead_wall_tiles).

    Dead wall layout (preserves existing convention):
      top row:    [0]  [1]  [2]  [3]  [4]  [5]  [6]    <- tops of 7 stacks
      bottom row: [7]  [8]  [9]  [10] [11] [12] [13]   <- bottoms of 7 stacks
      Dora indicators: indices 2, 3, 4, 5, 6
      Rinshan draws: from index 13 via pop()

    Live wall: tiles in dealing order (top, bottom per stack, starting from
    the stack left of the break going counter-clockwise).
    """
    break_info = compute_wall_break_info(dice, dealer_seat)
    break_stack = break_info.break_stack

    # Dead wall: 7 stacks from break going right (increasing, wrapping)
    dead_stacks = [(break_stack + i) % TOTAL_STACKS for i in range(DEAD_WALL_STACKS)]
    dead_wall_tiles = tuple(
        [tiles[s * 2] for s in dead_stacks]  # top row
        + [tiles[s * 2 + 1] for s in dead_stacks]  # bottom row
    )

    # Live wall: 61 stacks from (break-1) going left (decreasing, wrapping)
    live_stacks = [(break_stack - 1 - i) % TOTAL_STACKS for i in range(LIVE_WALL_STACKS)]
    live_tiles = tuple(tile for s in live_stacks for tile in (tiles[s * 2], tiles[s * 2 + 1]))

    return live_tiles, dead_wall_tiles


def create_wall(seed: str, round_number: int, dealer_seat: int) -> Wall:
    """
    Generate a shuffled wall with dice-determined break position.

    Shuffle tiles, roll dice, compute break position from dice + dealer_seat,
    then split tiles into live wall and dead wall based on the break.
    """
    shuffled, dice = generate_shuffled_wall_and_dice(seed, round_number)
    live_tiles, dead_wall_tiles = _split_wall_by_dice(shuffled, dice, dealer_seat)
    dora_indicators = (dead_wall_tiles[FIRST_DORA_INDEX],)
    return Wall(
        live_tiles=live_tiles,
        dead_wall_tiles=dead_wall_tiles,
        dora_indicators=dora_indicators,
        dice=dice,
    )


def create_wall_from_tiles(tiles: list[int], dice: tuple[int, int] = (1, 1)) -> Wall:
    """
    Create wall from explicit tile order (for tests/replays).

    Uses simple positional split (last 14 = dead wall, first 122 = live wall)
    without dice-based rotation. This lets tests control exactly which tiles
    go where without needing to compute break positions.

    The dice parameter stores the dice values as metadata for display tests.
    """
    if len(tiles) != TOTAL_WALL_SIZE:
        raise ValueError(f"Expected {TOTAL_WALL_SIZE} tiles, got {len(tiles)}")
    if not all(isinstance(t, int) and 0 <= t <= TOTAL_WALL_SIZE - 1 for t in tiles):
        raise ValueError(f"All tile IDs must be integers in [0, {TOTAL_WALL_SIZE - 1}]")
    if len(set(tiles)) != TOTAL_WALL_SIZE:
        raise ValueError("All tile IDs must be unique (full permutation)")

    dead_wall_tiles = tuple(tiles[-DEAD_WALL_SIZE:])
    live_tiles = tuple(tiles[:-DEAD_WALL_SIZE])
    dora_indicators = (dead_wall_tiles[FIRST_DORA_INDEX],)
    return Wall(
        live_tiles=live_tiles,
        dead_wall_tiles=dead_wall_tiles,
        dora_indicators=dora_indicators,
        dice=dice,
    )


def deal_initial_hands(wall: Wall, dealer_seat: int) -> tuple[Wall, list[list[int]]]:
    """
    Deal initial hands (13 tiles each) following mahjong dealing order.

    Deal order: starting from dealer, 4 tiles x 3 rounds, then 1 more each.
    Tiles dealt from front of live wall.
    Returns (updated_wall, hands) where hands is indexed by seat number (0-3),
    each hand sorted by tile ID.
    """
    min_tiles = NUM_PLAYERS * (TILES_PER_DEAL_BLOCK * DEAL_BLOCKS + TILES_PER_FINAL_DEAL)
    if len(wall.live_tiles) < min_tiles:
        raise ValueError(f"Live wall has {len(wall.live_tiles)} tiles, need at least {min_tiles} for dealing")

    live = list(wall.live_tiles)
    hands: list[list[int]] = [[] for _ in range(NUM_PLAYERS)]
    pos = 0

    # 3 rounds of 4 tiles each, starting from dealer
    for _ in range(DEAL_BLOCKS):
        for offset in range(NUM_PLAYERS):
            seat = (dealer_seat + offset) % NUM_PLAYERS
            hands[seat].extend(live[pos : pos + TILES_PER_DEAL_BLOCK])
            pos += TILES_PER_DEAL_BLOCK

    # 1 tile each for the final deal
    for offset in range(NUM_PLAYERS):
        seat = (dealer_seat + offset) % NUM_PLAYERS
        hands[seat].append(live[pos])
        pos += TILES_PER_FINAL_DEAL

    remaining_live = tuple(live[pos:])
    sorted_hands = [sort_tiles(hand) for hand in hands]

    new_wall = wall.model_copy(update={"live_tiles": remaining_live})
    return new_wall, sorted_hands


def draw_tile(wall: Wall) -> tuple[Wall, int | None]:
    """Draw from front of live wall. Returns (new_wall, tile) or (wall, None) if empty."""
    if not wall.live_tiles:
        return wall, None
    tile = wall.live_tiles[0]
    new_wall = wall.model_copy(update={"live_tiles": wall.live_tiles[1:]})
    return new_wall, tile


def draw_from_dead_wall(wall: Wall) -> tuple[Wall, int]:
    """
    Draw replacement tile from end of dead wall.

    Pops the last tile from the dead wall. If the live wall is not empty,
    replenishes the dead wall by moving the last tile from the live wall
    to the end of the dead wall to maintain its size.
    """
    if not wall.dead_wall_tiles:
        raise InvalidActionError("Dead wall is empty")

    dead = list(wall.dead_wall_tiles)
    tile = dead.pop()
    live = list(wall.live_tiles)

    # Replenish dead wall from end of live wall if possible
    if live:
        dead.append(live.pop())

    new_wall = wall.model_copy(
        update={
            "dead_wall_tiles": tuple(dead),
            "live_tiles": tuple(live),
        }
    )
    return new_wall, tile


def add_dora_indicator(wall: Wall) -> tuple[Wall, int]:
    """Reveal the next dora indicator from dead wall."""
    current_count = len(wall.dora_indicators)
    if current_count >= MAX_DORA_INDICATORS:
        raise InvalidActionError(f"Cannot add more than {MAX_DORA_INDICATORS} dora indicators")
    next_index = FIRST_DORA_INDEX + current_count
    if next_index >= len(wall.dead_wall_tiles):
        raise InvalidActionError("No more dora indicator positions in dead wall")
    indicator = wall.dead_wall_tiles[next_index]
    new_indicators = (*wall.dora_indicators, indicator)
    new_wall = wall.model_copy(update={"dora_indicators": new_indicators})
    return new_wall, indicator


def reveal_pending_dora(wall: Wall) -> tuple[Wall, list[int]]:
    """Reveal all pending dora indicators. Resets pending count to 0."""
    if wall.pending_dora_count == 0:
        return wall, []

    revealed: list[int] = []
    current_wall = wall
    for _ in range(wall.pending_dora_count):
        current_wall, indicator = add_dora_indicator(current_wall)
        revealed.append(indicator)

    current_wall = current_wall.model_copy(update={"pending_dora_count": 0})
    return current_wall, revealed


def increment_pending_dora(wall: Wall) -> Wall:
    """Increment pending dora count by 1 (for deferred kan dora)."""
    return wall.model_copy(update={"pending_dora_count": wall.pending_dora_count + 1})


def is_wall_exhausted(wall: Wall) -> bool:
    """Check if live wall is empty."""
    return len(wall.live_tiles) == 0


def tiles_remaining(wall: Wall) -> int:
    """Count tiles remaining in live wall."""
    return len(wall.live_tiles)


def collect_ura_dora_indicators(wall: Wall, *, include_kan_ura: bool, num_dora: int) -> list[int]:
    """
    Get ura dora indicator tile IDs for riichi winners.

    When include_kan_ura is False, return only 1 ura dora indicator.
    When True, return one per revealed dora indicator (up to num_dora).
    Returns empty list if dead wall or dora indicators are empty.
    """
    if not wall.dead_wall_tiles or not wall.dora_indicators:
        return []

    ura_count = 1 if not include_kan_ura else num_dora
    indicators: list[int] = []
    for i in range(ura_count):
        ura_index = URA_DORA_START_INDEX + i
        if ura_index < len(wall.dead_wall_tiles):
            indicators.append(wall.dead_wall_tiles[ura_index])
    return indicators
