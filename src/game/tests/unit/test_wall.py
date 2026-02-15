"""
Unit tests for Wall model and wall operations.

Covers wall creation, dealing, drawing, dora management, ura dora collection,
immutability, and edge cases.
"""

import pytest
from pydantic import ValidationError

from game.logic.exceptions import InvalidActionError
from game.logic.rng import SEED_BYTES, TOTAL_WALL_SIZE
from game.logic.wall import (
    DEAD_WALL_SIZE,
    DEAD_WALL_STACKS,
    FIRST_DORA_INDEX,
    LIVE_WALL_STACKS,
    MAX_DORA_INDICATORS,
    TOTAL_STACKS,
    URA_DORA_START_INDEX,
    Wall,
    _split_wall_by_dice,
    add_dora_indicator,
    collect_ura_dora_indicators,
    compute_wall_break_info,
    create_wall,
    create_wall_from_tiles,
    deal_initial_hands,
    draw_from_dead_wall,
    draw_tile,
    increment_pending_dora,
    is_wall_exhausted,
    reveal_pending_dora,
    tiles_remaining,
)

FIXED_SEED = "ab" * SEED_BYTES


def _make_tile_list() -> list[int]:
    """Create a standard 0-135 tile list for testing."""
    return list(range(TOTAL_WALL_SIZE))


class TestCreateWall:
    def test_has_correct_sizes(self):
        """Live wall = 122 tiles, dead wall = 14 tiles, 1 initial dora indicator."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert len(wall.live_tiles) == TOTAL_WALL_SIZE - DEAD_WALL_SIZE
        assert len(wall.dead_wall_tiles) == DEAD_WALL_SIZE
        assert len(wall.dora_indicators) == 1

    def test_all_tiles_present(self):
        """All 136 tile IDs present across live + dead wall."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        all_tiles = list(wall.live_tiles) + list(wall.dead_wall_tiles)
        assert sorted(all_tiles) == list(range(TOTAL_WALL_SIZE))

    def test_initial_dora_from_dead_wall(self):
        """Initial dora indicator is dead wall tile at FIRST_DORA_INDEX."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert wall.dora_indicators[0] == wall.dead_wall_tiles[FIRST_DORA_INDEX]

    def test_pending_dora_starts_at_zero(self):
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert wall.pending_dora_count == 0

    def test_deterministic(self):
        """Same seed + round produces the same wall."""
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall2 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert wall1 == wall2

    def test_different_seeds_different_walls(self):
        seed2 = "cd" * SEED_BYTES
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall2 = create_wall(seed2, 0, dealer_seat=0)
        assert wall1.live_tiles != wall2.live_tiles

    def test_different_rounds_different_walls(self):
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall2 = create_wall(FIXED_SEED, 1, dealer_seat=0)
        assert wall1.live_tiles != wall2.live_tiles


class TestCreateWallFromTiles:
    def test_explicit_tile_order_preserved(self):
        """Tile positions match the input order."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        # First 122 tiles go to live wall, last 14 to dead wall
        assert wall.live_tiles == tuple(range(122))
        assert wall.dead_wall_tiles == tuple(range(122, 136))

    def test_initial_dora_indicator(self):
        """Dora indicator set from dead wall index 2."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        assert wall.dora_indicators == (tiles[-DEAD_WALL_SIZE + FIRST_DORA_INDEX],)

    def test_too_few_tiles(self):
        with pytest.raises(ValueError, match="Expected 136"):
            create_wall_from_tiles(list(range(10)))

    def test_too_many_tiles(self):
        with pytest.raises(ValueError, match="Expected 136"):
            create_wall_from_tiles(list(range(200)))

    def test_duplicate_tiles(self):
        tiles = [0] * TOTAL_WALL_SIZE
        with pytest.raises(ValueError, match="unique"):
            create_wall_from_tiles(tiles)

    def test_out_of_range_tile_ids(self):
        tiles = list(range(TOTAL_WALL_SIZE))
        tiles[0] = 999
        with pytest.raises(ValueError, match="integers in"):
            create_wall_from_tiles(tiles)

    def test_negative_tile_ids(self):
        tiles = list(range(TOTAL_WALL_SIZE))
        tiles[0] = -1
        with pytest.raises(ValueError, match="integers in"):
            create_wall_from_tiles(tiles)


class TestDealInitialHands:
    def test_tile_counts(self):
        """Each player gets 13 tiles."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        _new_wall, hands = deal_initial_hands(wall, dealer_seat=0)
        for hand in hands:
            assert len(hand) == 13

    def test_dealing_order(self):
        """Dealer (seat 0) gets tiles first in each dealing block."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        _, hands = deal_initial_hands(wall, dealer_seat=0)
        # Dealer should get tiles 0-3 in first block
        first_block = list(range(4))
        for t in first_block:
            assert t in hands[0]

    def test_dealing_order_with_nonzero_dealer(self):
        """Dealing starts from the dealer seat, wrapping around."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        _, hands = deal_initial_hands(wall, dealer_seat=2)
        # Seat 2 (dealer) should get tiles 0-3 in first block
        first_block = list(range(4))
        for t in first_block:
            assert t in hands[2]

    def test_reduces_live_wall(self):
        """52 tiles (4 players x 13) removed from live wall."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        new_wall, _ = deal_initial_hands(wall, dealer_seat=0)
        assert len(new_wall.live_tiles) == len(wall.live_tiles) - 52

    def test_hands_are_sorted(self):
        """Each dealt hand is sorted by tile ID."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        _, hands = deal_initial_hands(wall, dealer_seat=0)
        for hand in hands:
            assert hand == sorted(hand)

    def test_all_dealt_tiles_unique(self):
        """No duplicate tiles across all dealt hands."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        _, hands = deal_initial_hands(wall, dealer_seat=0)
        all_dealt = [t for hand in hands for t in hand]
        assert len(all_dealt) == len(set(all_dealt))

    def test_insufficient_tiles(self):
        """Raises ValueError if live wall has fewer than 52 tiles."""
        wall = Wall(live_tiles=tuple(range(10)), dead_wall_tiles=tuple(range(14)))
        with pytest.raises(ValueError, match="need at least"):
            deal_initial_hands(wall, dealer_seat=0)


class TestDrawTile:
    def test_from_front(self):
        """Draws the first tile from the live wall."""
        wall = Wall(live_tiles=(10, 20, 30), dead_wall_tiles=())
        new_wall, tile = draw_tile(wall)
        assert tile == 10
        assert new_wall.live_tiles == (20, 30)

    def test_empty_wall(self):
        """Returns None when live wall is empty."""
        wall = Wall(live_tiles=(), dead_wall_tiles=())
        result_wall, tile = draw_tile(wall)
        assert tile is None
        assert result_wall is wall

    def test_last_tile(self):
        """Drawing the last tile leaves an empty live wall."""
        wall = Wall(live_tiles=(42,), dead_wall_tiles=())
        new_wall, tile = draw_tile(wall)
        assert tile == 42
        assert new_wall.live_tiles == ()

    def test_does_not_modify_dead_wall(self):
        """Drawing from live wall does not affect dead wall."""
        wall = Wall(live_tiles=(10, 20), dead_wall_tiles=(50, 60))
        new_wall, _ = draw_tile(wall)
        assert new_wall.dead_wall_tiles == wall.dead_wall_tiles


class TestDrawFromDeadWall:
    def test_pops_last(self):
        """Returns the last dead wall tile."""
        dead = tuple(range(14))
        wall = Wall(live_tiles=tuple(range(14, 24)), dead_wall_tiles=dead)
        _new_wall, tile = draw_from_dead_wall(wall)
        assert tile == 13  # last element

    def test_replenishes(self):
        """Dead wall size is maintained by moving last live tile to dead wall."""
        dead = tuple(range(14))
        live = tuple(range(14, 24))
        wall = Wall(live_tiles=live, dead_wall_tiles=dead)
        new_wall, _ = draw_from_dead_wall(wall)
        assert len(new_wall.dead_wall_tiles) == 14
        # Last live tile moved to dead wall
        assert new_wall.dead_wall_tiles[-1] == 23  # last of live
        assert len(new_wall.live_tiles) == len(live) - 1

    def test_empty_live_wall(self):
        """When live wall is empty, dead wall shrinks (no replenishment)."""
        dead = tuple(range(14))
        wall = Wall(live_tiles=(), dead_wall_tiles=dead)
        new_wall, tile = draw_from_dead_wall(wall)
        assert tile == 13
        assert len(new_wall.dead_wall_tiles) == 13

    def test_empty_dead_wall(self):
        """Raises InvalidActionError when dead wall is empty."""
        wall = Wall(live_tiles=(1, 2, 3), dead_wall_tiles=())
        with pytest.raises(InvalidActionError, match="empty"):
            draw_from_dead_wall(wall)


class TestAddDoraIndicator:
    def test_positions(self):
        """Dora indicators come from dead wall indices 2, 3, 4, 5, 6."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
        )
        indicators = [dead[FIRST_DORA_INDEX]]
        current_wall = wall
        for expected_idx in range(FIRST_DORA_INDEX + 1, FIRST_DORA_INDEX + MAX_DORA_INDICATORS):
            current_wall, ind = add_dora_indicator(current_wall)
            indicators.append(ind)
            assert ind == dead[expected_idx]

        assert len(indicators) == MAX_DORA_INDICATORS

    def test_max_exceeded(self):
        """Raises InvalidActionError when max dora indicators reached."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=tuple(dead[FIRST_DORA_INDEX : FIRST_DORA_INDEX + MAX_DORA_INDICATORS]),
        )
        with pytest.raises(InvalidActionError, match="Cannot add more"):
            add_dora_indicator(wall)

    def test_accumulates_indicators(self):
        """Each call adds one indicator to the tuple."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
        )
        new_wall, _ = add_dora_indicator(wall)
        assert len(new_wall.dora_indicators) == 2

    def test_short_dead_wall_raises(self):
        """Raises InvalidActionError when dead wall lacks the next indicator position."""
        # Dead wall with only 3 tiles (positions 0, 1, 2); next indicator at index 3 is missing
        dead = (50, 51, 52)
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
        )
        with pytest.raises(InvalidActionError, match="No more dora indicator positions"):
            add_dora_indicator(wall)


class TestRevealPendingDora:
    def test_reveals_correct_count(self):
        """Reveals the exact number of pending dora and resets count to 0."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
            pending_dora_count=2,
        )
        new_wall, revealed = reveal_pending_dora(wall)
        assert len(revealed) == 2
        assert new_wall.pending_dora_count == 0
        assert len(new_wall.dora_indicators) == 3  # 1 initial + 2 revealed

    def test_none_pending(self):
        """No-op when no pending dora."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
            pending_dora_count=0,
        )
        result_wall, revealed = reveal_pending_dora(wall)
        assert revealed == []
        assert result_wall is wall

    def test_revealed_values_match_dead_wall_positions(self):
        """Revealed dora indicators come from the correct dead wall positions."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
            pending_dora_count=1,
        )
        _, revealed = reveal_pending_dora(wall)
        assert revealed[0] == dead[FIRST_DORA_INDEX + 1]


class TestIncrementPendingDora:
    def test_increments_by_one(self):
        wall = Wall(pending_dora_count=0)
        new_wall = increment_pending_dora(wall)
        assert new_wall.pending_dora_count == 1

    def test_increments_from_nonzero(self):
        wall = Wall(pending_dora_count=2)
        new_wall = increment_pending_dora(wall)
        assert new_wall.pending_dora_count == 3


class TestIsWallExhausted:
    def test_empty(self):
        wall = Wall(live_tiles=())
        assert is_wall_exhausted(wall) is True

    def test_not_empty(self):
        wall = Wall(live_tiles=(1,))
        assert is_wall_exhausted(wall) is False


class TestTilesRemaining:
    def test_correct_count(self):
        wall = Wall(live_tiles=(1, 2, 3, 4, 5))
        assert tiles_remaining(wall) == 5

    def test_empty(self):
        wall = Wall(live_tiles=())
        assert tiles_remaining(wall) == 0

    def test_full_wall(self):
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        assert tiles_remaining(wall) == TOTAL_WALL_SIZE - DEAD_WALL_SIZE


class TestCollectUraDoraIndicators:
    def test_basic_ura_dora(self):
        """Collects ura dora from bottom row of dead wall."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=False, num_dora=1)
        assert ura == [dead[URA_DORA_START_INDEX]]

    def test_no_kan_ura(self):
        """Without kan ura, returns only 1 indicator regardless of num_dora."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=tuple(dead[FIRST_DORA_INDEX : FIRST_DORA_INDEX + 3]),
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=False, num_dora=3)
        assert len(ura) == 1

    def test_with_kan_ura(self):
        """With kan ura, returns one per revealed dora indicator."""
        dead = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=tuple(dead[FIRST_DORA_INDEX : FIRST_DORA_INDEX + 3]),
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True, num_dora=3)
        assert len(ura) == 3
        for i in range(3):
            assert ura[i] == dead[URA_DORA_START_INDEX + i]

    def test_empty_dead_wall(self):
        """Returns empty list when dead wall is empty."""
        wall = Wall(live_tiles=(), dead_wall_tiles=(), dora_indicators=())
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True, num_dora=1)
        assert ura == []

    def test_empty_dora_indicators(self):
        """Returns empty list when dora indicators are empty."""
        wall = Wall(live_tiles=(), dead_wall_tiles=tuple(range(14)), dora_indicators=())
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True, num_dora=1)
        assert ura == []

    def test_ura_index_beyond_dead_wall(self):
        """Handles case where ura dora index exceeds dead wall length."""
        # Short dead wall of 8 tiles: ura dora at index 7 exists, but 8+ don't
        dead = tuple(range(100, 108))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX], dead[FIRST_DORA_INDEX + 1]),
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True, num_dora=2)
        # Only index 7 is within bounds, index 8 is out of bounds
        assert len(ura) == 1
        assert ura[0] == dead[URA_DORA_START_INDEX]


class TestWallImmutability:
    def test_frozen_model(self):
        """Wall is frozen - direct attribute assignment raises."""
        wall = Wall(live_tiles=(1, 2, 3))
        with pytest.raises(ValidationError, match="frozen"):
            wall.live_tiles = (4, 5, 6)

    def test_model_copy_works(self):
        """model_copy creates a new Wall with updated fields."""
        wall = Wall(live_tiles=(1, 2, 3), pending_dora_count=0)
        new_wall = wall.model_copy(update={"pending_dora_count": 1})
        assert new_wall.pending_dora_count == 1
        assert wall.pending_dora_count == 0

    def test_operations_return_new_instances(self):
        """Wall operations return new Wall instances, not mutations."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        new_wall, _ = draw_tile(wall)
        assert new_wall is not wall
        assert len(new_wall.live_tiles) == len(wall.live_tiles) - 1
        # Original unchanged
        assert len(wall.live_tiles) == TOTAL_WALL_SIZE - DEAD_WALL_SIZE


class TestComputeWallBreakInfo:
    def test_dealer_east_sum_5(self):
        """Sum 5, dealer 0 -> target 0 (East/dealer)."""
        info = compute_wall_break_info((2, 3), dealer_seat=0)
        assert info.dice_sum == 5
        assert info.target_seat == 0

    def test_dealer_east_sum_2(self):
        """Sum 2, dealer 0 -> target 1 (South)."""
        info = compute_wall_break_info((1, 1), dealer_seat=0)
        assert info.dice_sum == 2
        assert info.target_seat == 1

    def test_dealer_east_sum_7(self):
        """Sum 7, dealer 0 -> target 2 (West)."""
        info = compute_wall_break_info((3, 4), dealer_seat=0)
        assert info.dice_sum == 7
        assert info.target_seat == 2

    def test_dealer_east_sum_4(self):
        """Sum 4, dealer 0 -> target 3 (North)."""
        info = compute_wall_break_info((2, 2), dealer_seat=0)
        assert info.dice_sum == 4
        assert info.target_seat == 3

    def test_all_sums(self):
        """Verify target seat for all dice sums 2-12 with dealer 0."""
        # Maps dice_sum -> (dice_pair, expected_target_seat)
        # All dice values are valid (1-6)
        test_cases = {
            2: ((1, 1), 1),
            3: ((1, 2), 2),
            4: ((2, 2), 3),
            5: ((2, 3), 0),
            6: ((3, 3), 1),
            7: ((3, 4), 2),
            8: ((4, 4), 3),
            9: ((4, 5), 0),
            10: ((5, 5), 1),
            11: ((5, 6), 2),
            12: ((6, 6), 3),
        }
        for dice_sum, (dice, expected_target) in test_cases.items():
            info = compute_wall_break_info(dice, dealer_seat=0)
            assert info.target_seat == expected_target, (
                f"Sum {dice_sum}: expected target {expected_target}, got {info.target_seat}"
            )

    def test_rotated_dealer(self):
        """dealer_seat != 0 rotates targets correctly."""
        # dealer=1, sum=5 -> target = (1+5-1)%4 = 1 (dealer itself)
        info = compute_wall_break_info((2, 3), dealer_seat=1)
        assert info.target_seat == 1
        # dealer=2, sum=2 -> target = (2+2-1)%4 = 3
        info = compute_wall_break_info((1, 1), dealer_seat=2)
        assert info.target_seat == 3

    def test_break_stack_range(self):
        """break_stack always in [0, 67]."""
        for dealer in range(4):
            for d1 in range(1, 7):
                for d2 in range(1, 7):
                    info = compute_wall_break_info((d1, d2), dealer_seat=dealer)
                    assert 0 <= info.break_stack < TOTAL_STACKS

    def test_break_stack_values(self):
        """Specific break_stack values for known dice+dealer combos."""
        # dealer=0, dice=(3,4)=7: target=2, break_stack = (3*17-7)%68 = 44
        info = compute_wall_break_info((3, 4), dealer_seat=0)
        assert info.break_stack == 44
        # dealer=0, dice=(1,1)=2: target=1, break_stack = (2*17-2)%68 = 32
        info = compute_wall_break_info((1, 1), dealer_seat=0)
        assert info.break_stack == 32
        # dealer=0, dice=(6,6)=12: target=3, break_stack = (4*17-12)%68 = 56
        info = compute_wall_break_info((6, 6), dealer_seat=0)
        assert info.break_stack == 56


class TestSplitWallByDice:
    def test_dead_wall_layout(self):
        """Dead wall tuple has correct layout: indices 0-6 = tops, indices 7-13 = bottoms."""
        tiles = _make_tile_list()
        # dealer=0, dice=(3,4)=7 -> break_stack=44
        _live, dead = _split_wall_by_dice(tiles, (3, 4), dealer_seat=0)
        # Dead stacks: 44, 45, 46, 47, 48, 49, 50
        expected_tops = [tiles[s * 2] for s in range(44, 51)]
        expected_bottoms = [tiles[s * 2 + 1] for s in range(44, 51)]
        assert list(dead[:7]) == expected_tops
        assert list(dead[7:]) == expected_bottoms

    def test_live_wall_order(self):
        """Live wall tiles follow dealing order: stack left of break going counter-clockwise."""
        tiles = _make_tile_list()
        # dealer=0, dice=(3,4)=7 -> break_stack=44
        live, _ = _split_wall_by_dice(tiles, (3, 4), dealer_seat=0)
        # First live stack is 43 (break-1), going down
        assert live[0] == tiles[43 * 2]  # top of stack 43
        assert live[1] == tiles[43 * 2 + 1]  # bottom of stack 43
        assert live[2] == tiles[42 * 2]  # top of stack 42
        assert live[3] == tiles[42 * 2 + 1]  # bottom of stack 42

    def test_wrapping(self):
        """dice_sum=2 causes dead wall to wrap from one player's segment to next."""
        tiles = _make_tile_list()
        # dealer=0, dice=(1,1)=2 -> target=1, break_stack=32
        live, dead = _split_wall_by_dice(tiles, (1, 1), dealer_seat=0)
        # Dead stacks: 32, 33, 34, 35, 36, 37, 38 (wraps from South into West)
        dead_stacks = [32, 33, 34, 35, 36, 37, 38]
        expected_tops = [tiles[s * 2] for s in dead_stacks]
        assert list(dead[:7]) == expected_tops
        # Live starts at stack 31, going down, eventually wraps to 67
        assert live[0] == tiles[31 * 2]

    def test_known_values(self):
        """With sequential tiles (0-135) and specific dice+dealer, verify exact tile IDs."""
        tiles = _make_tile_list()
        # dealer=0, dice=(6,6)=12 -> break_stack=56
        live, dead = _split_wall_by_dice(tiles, (6, 6), dealer_seat=0)
        # Dead stacks: 56, 57, 58, 59, 60, 61, 62
        assert dead[0] == tiles[56 * 2]  # = 112 (top of stack 56)
        assert dead[6] == tiles[62 * 2]  # = 124 (top of stack 62)
        assert dead[7] == tiles[56 * 2 + 1]  # = 113 (bottom of stack 56)
        # All tiles accounted for
        all_tiles = list(live) + list(dead)
        assert sorted(all_tiles) == list(range(TOTAL_WALL_SIZE))

    def test_sizes(self):
        """Live wall always 122, dead wall always 14 regardless of dice."""
        tiles = _make_tile_list()
        for d1 in range(1, 7):
            for d2 in range(1, 7):
                live, dead = _split_wall_by_dice(tiles, (d1, d2), dealer_seat=0)
                assert len(live) == LIVE_WALL_STACKS * 2  # 122
                assert len(dead) == DEAD_WALL_STACKS * 2  # 14

    def test_all_tiles_present(self):
        """Union of live + dead wall contains all 136 tile IDs."""
        tiles = _make_tile_list()
        live, dead = _split_wall_by_dice(tiles, (4, 5), dealer_seat=2)
        all_tiles = list(live) + list(dead)
        assert sorted(all_tiles) == list(range(TOTAL_WALL_SIZE))


class TestCreateWallWithDice:
    def test_has_dice(self):
        """Dice values are stored on wall, both in [1, 6]."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert 1 <= wall.dice[0] <= 6
        assert 1 <= wall.dice[1] <= 6

    def test_deterministic(self):
        """Same seed+round+dealer produces the same dice and wall split."""
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall2 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert wall1 == wall2
        assert wall1.dice == wall2.dice

    def test_sizes_with_dice(self):
        """Live wall = 122, dead wall = 14 regardless of dice."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert len(wall.live_tiles) == TOTAL_WALL_SIZE - DEAD_WALL_SIZE
        assert len(wall.dead_wall_tiles) == DEAD_WALL_SIZE

    def test_all_tiles_present(self):
        """Union of live + dead wall contains all 136 tile IDs."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        all_tiles = list(wall.live_tiles) + list(wall.dead_wall_tiles)
        assert sorted(all_tiles) == list(range(TOTAL_WALL_SIZE))

    def test_different_dealer_seats_different_splits(self):
        """Same seed+round but different dealer_seat produces different live/dead wall."""
        wall0 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=1)
        # Dice are the same (same RNG stream), but break position differs
        assert wall0.dice == wall1.dice
        assert wall0.live_tiles != wall1.live_tiles


class TestCreateWallFromTilesWithDice:
    def test_default_dice(self):
        """Dice defaults to (1, 1) with simple positional split."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        assert wall.dice == (1, 1)

    def test_custom_dice(self):
        """Custom dice values are preserved as metadata."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles, dice=(3, 5))
        assert wall.dice == (3, 5)
        # Simple split is unchanged regardless of dice
        assert wall.live_tiles == tuple(range(122))
        assert wall.dead_wall_tiles == tuple(range(122, 136))
