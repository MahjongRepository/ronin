from pydantic import BaseModel, ConfigDict, model_validator

from game.logic.rng import generate_shuffled_wall_and_dice
from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES, sort_tiles

TILES_PER_STACK = 2
DEAD_WALL_STACKS = 7
DEAD_WALL_SIZE = DEAD_WALL_STACKS * TILES_PER_STACK
RINSHAN_STACKS = 2
MAX_RINSHAN_DRAWS = RINSHAN_STACKS * TILES_PER_STACK
MAX_DORA_INDICATORS = DEAD_WALL_STACKS - RINSHAN_STACKS
TILES_PER_DEAL_BLOCK = 4
DEAL_BLOCKS = 3
TILES_PER_FINAL_DEAL = 1

STACKS_PER_PLAYER = 17
TOTAL_STACKS = NUM_PLAYERS * STACKS_PER_PLAYER
LIVE_WALL_STACKS = TOTAL_STACKS - DEAD_WALL_STACKS


class TileStack(BaseModel):
    """
    One two-tile stack of the wall: the top tile is drawn or shown first, the bottom tile lies under it.
    """

    model_config = ConfigDict(frozen=True)

    top: int
    bottom: int


class DeadWall(BaseModel):
    """
    The 14 tiles set aside at the wall break, by role.

    Seven stacks counted from the break: the two nearest supply the rinshan (kan replacement) tiles, the other five
    are the indicator stacks, each showing its dora on top with the ura dora beneath. A rinshan draw pulls the last
    live tile into the undrawable reserve, so the dead wall always holds 14 tiles. Dora reveals are a count over the
    indicator stacks, so a dora and its ura can never come from different stacks.
    """

    model_config = ConfigDict(frozen=True)

    rinshan: tuple[int, ...]
    indicators: tuple[TileStack, ...]
    reserve: tuple[int, ...]
    revealed_count: int = 1
    pending_reveals: int = 0

    @model_validator(mode="after")
    def _check_partition(self) -> DeadWall:
        if len(self.indicators) != MAX_DORA_INDICATORS:
            raise ValueError(f"dead wall needs {MAX_DORA_INDICATORS} indicator stacks, got {len(self.indicators)}")

        if len(self.rinshan) + len(self.reserve) != MAX_RINSHAN_DRAWS:
            raise ValueError(f"rinshan tiles plus reserve must total {MAX_RINSHAN_DRAWS}")

        if not (1 <= self.revealed_count <= MAX_DORA_INDICATORS):
            raise ValueError(f"revealed_count must be in [1, {MAX_DORA_INDICATORS}], got {self.revealed_count}")

        if self.pending_reveals < 0 or self.revealed_count + self.pending_reveals > MAX_DORA_INDICATORS:
            raise ValueError("revealed and pending dora together cannot exceed the indicator stacks")

        tiles = self.tiles
        if len(set(tiles)) != DEAD_WALL_SIZE or not all(0 <= t < NUM_TILES for t in tiles):
            raise ValueError("dead wall must hold 14 distinct tile ids")

        return self

    @property
    def tiles(self) -> tuple[int, ...]:
        """
        Every tile the dead wall currently owns.
        """
        stacked = tuple(t for stack in self.indicators for t in (stack.top, stack.bottom))
        return (*self.rinshan, *stacked, *self.reserve)

    @property
    def dora_indicators(self) -> tuple[int, ...]:
        """
        The revealed dora indicators, in reveal order.
        """
        return tuple(stack.top for stack in self.indicators[: self.revealed_count])

    @property
    def ura_dora_indicators(self) -> tuple[int, ...]:
        """
        The ura dora under each revealed indicator, in the same order.
        """
        return tuple(stack.bottom for stack in self.indicators[: self.revealed_count])


class Wall(BaseModel):
    """
    Immutable wall state for a mahjong round: the live wall in draw order, the dead wall and the break dice.
    """

    model_config = ConfigDict(frozen=True)

    live_tiles: tuple[int, ...]
    dead_wall: DeadWall
    dice: tuple[int, int] = (1, 1)

    @property
    def dora_indicators(self) -> tuple[int, ...]:
        """
        The revealed dora indicators, in reveal order.
        """
        return self.dead_wall.dora_indicators

    @property
    def pending_dora_count(self) -> int:
        """
        Kan dora reveals deferred until the kan caller's discard settles.
        """
        return self.dead_wall.pending_reveals


class WallBreakInfo(BaseModel):
    """
    Computed wall break position from dice roll.
    """

    model_config = ConfigDict(frozen=True)

    dice_sum: int
    target_seat: int
    break_stack: int


def compute_wall_break_info(dice: tuple[int, int], dealer_seat: int) -> WallBreakInfo:
    """
    Compute wall break position from dice roll and dealer seat.

    Target seat: count counter-clockwise from dealer by (dice_sum - 1). Break stack: count dice_sum stacks from the
    right end of the target player's wall segment; the 7 stacks starting there (going right, wrapping) form the dead
    wall.
    """
    dice_sum = dice[0] + dice[1]
    target_seat = (dealer_seat + dice_sum - 1) % NUM_PLAYERS
    break_stack = ((target_seat + 1) * STACKS_PER_PLAYER - dice_sum) % TOTAL_STACKS
    return WallBreakInfo(dice_sum=dice_sum, target_seat=target_seat, break_stack=break_stack)


def _split_wall_by_dice(tiles: list[int], dice: tuple[int, int], dealer_seat: int) -> tuple[list[int], list[TileStack]]:
    """
    Split 136 shuffled tiles into the live wall (draw order) and the seven dead wall stacks (from the break outward).

    The tiles list is 68 stacks of 2 in a ring, tile 2s on top of tile 2s+1; seat s owns stacks 17s..17s+16 with the
    higher index at its right. The live wall starts at the stack left of the break and moves away from the dead wall,
    which is clockwise around the table.
    """
    if len(tiles) != NUM_TILES:
        raise ValueError(f"Expected {NUM_TILES} tiles, got {len(tiles)}")

    break_stack = compute_wall_break_info(dice, dealer_seat).break_stack
    dead_stacks = [
        TileStack(top=tiles[s * 2], bottom=tiles[s * 2 + 1])
        for s in ((break_stack + i) % TOTAL_STACKS for i in range(DEAD_WALL_STACKS))
    ]
    live_stacks = [(break_stack - 1 - i) % TOTAL_STACKS for i in range(LIVE_WALL_STACKS)]
    live_tiles = [tile for s in live_stacks for tile in (tiles[s * 2], tiles[s * 2 + 1])]
    return live_tiles, dead_stacks


def build_dead_wall(stacks: list[TileStack]) -> DeadWall:
    """
    Assign roles to the seven dead wall stacks counted from the break: two rinshan stacks, then five indicator stacks.

    Rinshan tiles are drawn top then bottom of the nearest stack first.
    """
    if len(stacks) != DEAD_WALL_STACKS:
        raise ValueError(f"Expected {DEAD_WALL_STACKS} dead wall stacks, got {len(stacks)}")

    rinshan = tuple(t for stack in stacks[:RINSHAN_STACKS] for t in (stack.top, stack.bottom))
    return DeadWall(rinshan=rinshan, indicators=tuple(stacks[RINSHAN_STACKS:]), reserve=())


def create_wall(*, seed: str, round_number: int, dealer_seat: int) -> Wall:
    """
    Generate a shuffled wall with dice-determined break position.
    """
    shuffled, dice = generate_shuffled_wall_and_dice(seed, round_number)
    live_tiles, dead_stacks = _split_wall_by_dice(shuffled, dice, dealer_seat)
    return Wall(live_tiles=tuple(live_tiles), dead_wall=build_dead_wall(dead_stacks), dice=dice)


def create_wall_from_tiles(tiles: list[int]) -> Wall:
    """
    Create a wall from an explicit tile order (tests and replays).

    The first 122 tiles are the live wall in draw order; the last 14 are the dead wall stacks in break order, tops first
    (positions 122-128) then bottoms (129-135), without dice-based rotation.
    """
    if len(tiles) != NUM_TILES:
        raise ValueError(f"Expected {NUM_TILES} tiles, got {len(tiles)}")

    if not all(isinstance(t, int) and 0 <= t < NUM_TILES for t in tiles):
        raise ValueError(f"All tile IDs must be integers in [0, {NUM_TILES - 1}]")

    if len(set(tiles)) != NUM_TILES:
        raise ValueError("All tile IDs must be unique (full permutation)")

    dead = tiles[-DEAD_WALL_SIZE:]
    stacks = [TileStack(top=dead[i], bottom=dead[i + DEAD_WALL_STACKS]) for i in range(DEAD_WALL_STACKS)]
    return Wall(live_tiles=tuple(tiles[:-DEAD_WALL_SIZE]), dead_wall=build_dead_wall(stacks))


def deal_initial_hands(wall: Wall, dealer_seat: int) -> tuple[Wall, list[list[int]]]:
    """
    Deal initial hands (13 tiles each) following mahjong dealing order.

    Deal order: starting from dealer, 4 tiles x 3 rounds, then 1 more each. Tiles dealt from front of live wall.
    Returns (updated_wall, hands) where hands is indexed by seat number (0-3), each hand sorted by tile ID.
    """
    min_tiles = NUM_PLAYERS * (TILES_PER_DEAL_BLOCK * DEAL_BLOCKS + TILES_PER_FINAL_DEAL)
    if len(wall.live_tiles) < min_tiles:
        raise ValueError(f"Live wall has {len(wall.live_tiles)} tiles, need at least {min_tiles} for dealing")

    live = list(wall.live_tiles)
    hands: list[list[int]] = [[] for _ in range(NUM_PLAYERS)]
    pos = 0
    for _ in range(DEAL_BLOCKS):
        for offset in range(NUM_PLAYERS):
            seat = (dealer_seat + offset) % NUM_PLAYERS
            hands[seat].extend(live[pos : pos + TILES_PER_DEAL_BLOCK])
            pos += TILES_PER_DEAL_BLOCK

    for offset in range(NUM_PLAYERS):
        seat = (dealer_seat + offset) % NUM_PLAYERS
        hands[seat].append(live[pos])
        pos += TILES_PER_FINAL_DEAL

    new_wall = wall.model_copy(update={"live_tiles": tuple(live[pos:])})
    return new_wall, [sort_tiles(hand) for hand in hands]


def draw_tile(wall: Wall) -> tuple[Wall, int | None]:
    """
    Draw from front of live wall.

    Returns (new_wall, tile) or (wall, None) if empty.
    """
    if not wall.live_tiles:
        return wall, None

    return wall.model_copy(update={"live_tiles": wall.live_tiles[1:]}), wall.live_tiles[0]


def draw_from_dead_wall(wall: Wall) -> tuple[Wall, int]:
    """
    Draw the next rinshan tile after a kan and move the last live tile into the dead wall's reserve.
    """
    dead = wall.dead_wall
    if not dead.rinshan:
        raise AssertionError("No more rinshan draw positions available")

    if not wall.live_tiles:
        raise AssertionError("Cannot draw from dead wall: live wall is empty for replenishment")

    tile, *remaining = dead.rinshan
    new_dead = DeadWall(
        rinshan=tuple(remaining),
        indicators=dead.indicators,
        reserve=(*dead.reserve, wall.live_tiles[-1]),
        revealed_count=dead.revealed_count,
        pending_reveals=dead.pending_reveals,
    )
    return wall.model_copy(update={"live_tiles": wall.live_tiles[:-1], "dead_wall": new_dead}), tile


def _with_reveals(dead: DeadWall, *, revealed_count: int, pending_reveals: int) -> DeadWall:
    return DeadWall(
        rinshan=dead.rinshan,
        indicators=dead.indicators,
        reserve=dead.reserve,
        revealed_count=revealed_count,
        pending_reveals=pending_reveals,
    )


def add_dora_indicator(wall: Wall) -> tuple[Wall, int]:
    """
    Reveal the next dora indicator; returns the new wall and the indicator tile.
    """
    dead = wall.dead_wall
    if dead.revealed_count >= MAX_DORA_INDICATORS:
        raise AssertionError(f"Cannot add more than {MAX_DORA_INDICATORS} dora indicators")

    new_dead = _with_reveals(dead, revealed_count=dead.revealed_count + 1, pending_reveals=dead.pending_reveals)
    return wall.model_copy(update={"dead_wall": new_dead}), new_dead.dora_indicators[-1]


def increment_pending_dora(wall: Wall) -> Wall:
    """
    Defer one kan dora reveal until the kan caller's discard settles.
    """
    dead = wall.dead_wall
    if dead.revealed_count + dead.pending_reveals + 1 > MAX_DORA_INDICATORS:
        raise AssertionError(
            f"Cannot exceed {MAX_DORA_INDICATORS} dora indicators "
            f"(current: {dead.revealed_count}, pending: {dead.pending_reveals})",
        )

    new_dead = _with_reveals(dead, revealed_count=dead.revealed_count, pending_reveals=dead.pending_reveals + 1)
    return wall.model_copy(update={"dead_wall": new_dead})


def reveal_pending_dora(wall: Wall) -> tuple[Wall, list[int]]:
    """
    Reveal every deferred kan dora; returns the new wall and the indicators revealed, in order.
    """
    dead = wall.dead_wall
    if dead.pending_reveals == 0:
        return wall, []

    revealed_count = dead.revealed_count + dead.pending_reveals
    new_dead = _with_reveals(dead, revealed_count=revealed_count, pending_reveals=0)
    return wall.model_copy(update={"dead_wall": new_dead}), list(new_dead.dora_indicators[dead.revealed_count :])


def clear_pending_dora(wall: Wall) -> Wall:
    """
    Drop deferred kan dora reveals without revealing them (a tsumo on the rinshan tile scores before they show).
    """
    dead = wall.dead_wall
    if dead.pending_reveals == 0:
        return wall

    return wall.model_copy(
        update={"dead_wall": _with_reveals(dead, revealed_count=dead.revealed_count, pending_reveals=0)}
    )


def is_wall_exhausted(wall: Wall) -> bool:
    """
    Check if live wall is empty.
    """
    return len(wall.live_tiles) == 0


def tiles_remaining(wall: Wall) -> int:
    """
    Count tiles remaining in live wall.
    """
    return len(wall.live_tiles)


def collect_ura_dora_indicators(wall: Wall, *, include_kan_ura: bool) -> list[int]:
    """
    Get ura dora indicator tile IDs for riichi winners: one under the first indicator, or one per revealed indicator
    when include_kan_ura is set.
    """
    ura = wall.dead_wall.ura_dora_indicators
    return list(ura if include_kan_ura else ura[:1])
