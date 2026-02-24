"""
Unit tests for Wall model and wall operations.

Covers wall creation, dealing, drawing, dora management, ura dora collection,
and edge cases.
"""

import pytest

from game.logic.exceptions import InvalidActionError
from game.logic.rng import SEED_BYTES
from game.logic.tiles import NUM_TILES
from game.logic.wall import (
    DEAD_WALL_SIZE,
    DEAD_WALL_STACKS,
    FIRST_DORA_INDEX,
    LIVE_WALL_STACKS,
    MAX_DORA_INDICATORS,
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
    reveal_pending_dora,
)

FIXED_SEED = "ab" * SEED_BYTES


def _make_tile_list() -> list[int]:
    """Create a standard 0-135 tile list for testing."""
    return list(range(NUM_TILES))


class TestCreateWall:
    def test_has_correct_sizes(self):
        """Live wall = 122 tiles, dead wall = 14 tiles, 1 initial dora indicator."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert len(wall.live_tiles) == NUM_TILES - DEAD_WALL_SIZE
        assert len(wall.dead_wall_tiles) == DEAD_WALL_SIZE
        assert len(wall.dora_indicators) == 1

    def test_all_tiles_present(self):
        """All 136 tile IDs present across live + dead wall."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        all_tiles = list(wall.live_tiles) + list(wall.dead_wall_tiles)
        assert sorted(all_tiles) == list(range(NUM_TILES))

    def test_initial_dora_from_dead_wall(self):
        """Initial dora indicator is dead wall tile at FIRST_DORA_INDEX."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert wall.dora_indicators[0] == wall.dead_wall_tiles[FIRST_DORA_INDEX]

    def test_ura_dora_stored_eagerly(self):
        """Ura dora indicators are captured from dead wall at creation time."""
        wall = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert len(wall.ura_dora_indicators) == MAX_DORA_INDICATORS
        for i in range(MAX_DORA_INDICATORS):
            assert wall.ura_dora_indicators[i] == wall.dead_wall_tiles[URA_DORA_START_INDEX + i]

    def test_deterministic(self):
        """Same seed + round produces the same wall."""
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall2 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        assert wall1 == wall2

    def test_different_inputs_produce_different_walls(self):
        """Different seed or round produces different walls."""
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall2 = create_wall("cd" * SEED_BYTES, 0, dealer_seat=0)
        wall3 = create_wall(FIXED_SEED, 1, dealer_seat=0)
        assert wall1.live_tiles != wall2.live_tiles
        assert wall1.live_tiles != wall3.live_tiles

    def test_different_dealer_seats_different_splits(self):
        """Same seed+round but different dealer_seat produces different live/dead wall."""
        wall0 = create_wall(FIXED_SEED, 0, dealer_seat=0)
        wall1 = create_wall(FIXED_SEED, 0, dealer_seat=1)
        # Dice are the same (same RNG stream), but break position differs
        assert wall0.dice == wall1.dice
        assert wall0.live_tiles != wall1.live_tiles


class TestCreateWallFromTiles:
    def test_explicit_tile_order_preserved(self):
        """Tile positions match the input order."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        assert wall.live_tiles == tuple(range(122))
        assert wall.dead_wall_tiles == tuple(range(122, 136))

    def test_initial_dora_indicator(self):
        """Dora indicator set from dead wall index 2."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        assert wall.dora_indicators == (tiles[-DEAD_WALL_SIZE + FIRST_DORA_INDEX],)

    def test_ura_dora_stored_eagerly(self):
        """Ura dora indicators captured from dead wall positions 7-11."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        dead = wall.dead_wall_tiles
        expected = tuple(dead[URA_DORA_START_INDEX : URA_DORA_START_INDEX + MAX_DORA_INDICATORS])
        assert wall.ura_dora_indicators == expected

    def test_wrong_tile_count(self):
        with pytest.raises(ValueError, match="Expected 136"):
            create_wall_from_tiles(list(range(10)))
        with pytest.raises(ValueError, match="Expected 136"):
            create_wall_from_tiles(list(range(200)))

    def test_duplicate_tiles(self):
        tiles = [0] * NUM_TILES
        with pytest.raises(ValueError, match="unique"):
            create_wall_from_tiles(tiles)

    def test_out_of_range_tile_ids(self):
        tiles = list(range(NUM_TILES))
        tiles[0] = 999
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
        first_block = list(range(4))
        for t in first_block:
            assert t in hands[0]

    def test_dealing_order_with_nonzero_dealer(self):
        """Dealing starts from the dealer seat, wrapping around."""
        tiles = _make_tile_list()
        wall = create_wall_from_tiles(tiles)
        _, hands = deal_initial_hands(wall, dealer_seat=2)
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


class TestDrawFromDeadWall:
    def test_successive_draws_follow_right_to_left_order(self):
        """Rinshan draws proceed right-to-left: indices 13, 12, 11, 10."""
        dead = tuple(range(100, 114))
        live = tuple(range(50, 70))
        wall = Wall(live_tiles=live, dead_wall_tiles=dead)
        drawn_tiles = []
        current_wall = wall
        for _ in range(4):
            current_wall, tile = draw_from_dead_wall(current_wall)
            drawn_tiles.append(tile)
        assert drawn_tiles == [dead[13], dead[12], dead[11], dead[10]]

    def test_replenishes(self):
        """Dead wall size is maintained by placing live tile at the drawn position."""
        dead = tuple(range(14))
        live = tuple(range(14, 24))
        wall = Wall(live_tiles=live, dead_wall_tiles=dead)
        new_wall, _ = draw_from_dead_wall(wall)
        assert len(new_wall.dead_wall_tiles) == 14
        # Last live tile replaces the drawn position (index 13)
        assert new_wall.dead_wall_tiles[13] == 23
        assert len(new_wall.live_tiles) == len(live) - 1

    def test_increments_rinshan_draws_count(self):
        """Each draw increments the rinshan draw counter."""
        dead = tuple(range(14))
        live = tuple(range(14, 24))
        wall = Wall(live_tiles=live, dead_wall_tiles=dead)
        new_wall, _ = draw_from_dead_wall(wall)
        assert new_wall.rinshan_draws_count == 1
        new_wall2, _ = draw_from_dead_wall(new_wall)
        assert new_wall2.rinshan_draws_count == 2

    def test_empty_live_wall_raises(self):
        """Raises InvalidActionError when live wall is empty (cannot replenish)."""
        dead = tuple(range(14))
        wall = Wall(live_tiles=(), dead_wall_tiles=dead)
        with pytest.raises(InvalidActionError, match="live wall is empty"):
            draw_from_dead_wall(wall)

    def test_no_rinshan_positions_available(self):
        """Raises InvalidActionError when all 4 rinshan draws are exhausted."""
        dead = tuple(range(14))
        wall = Wall(live_tiles=(1, 2, 3), dead_wall_tiles=dead, rinshan_draws_count=4)
        with pytest.raises(InvalidActionError, match="No more rinshan"):
            draw_from_dead_wall(wall)

    def test_dead_wall_size_maintained_after_all_four_kan_draws(self):
        """Dead wall remains exactly 14 tiles after all 4 rinshan draws."""
        dead = tuple(range(100, 114))
        live = tuple(range(50, 70))
        wall = Wall(live_tiles=live, dead_wall_tiles=dead)
        current_wall = wall
        for draw_num in range(4):
            current_wall, _ = draw_from_dead_wall(current_wall)
            assert len(current_wall.dead_wall_tiles) == DEAD_WALL_SIZE, (
                f"Dead wall size wrong after draw {draw_num + 1}"
            )
        # live wall lost exactly 4 tiles (one per replenishment)
        assert len(current_wall.live_tiles) == len(live) - 4

    def test_dora_and_ura_positions_unaffected(self):
        """Dora (indices 2-6) and ura dora (indices 7-9) remain stable after rinshan draws."""
        dead = tuple(range(100, 114))
        live = tuple(range(50, 70))
        wall = Wall(live_tiles=live, dead_wall_tiles=dead)
        current_wall = wall
        for _ in range(4):
            current_wall, _ = draw_from_dead_wall(current_wall)
        # Dora indicator positions (2-6) and ura dora positions (7-9) are unchanged
        for i in range(2, 10):
            assert current_wall.dead_wall_tiles[i] == dead[i]


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

    def test_short_dead_wall_raises(self):
        """Raises InvalidActionError when dead wall lacks the next indicator position."""
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

    def test_rejects_exceeding_max_dora(self):
        """Raises InvalidActionError when total dora would exceed MAX_DORA_INDICATORS."""
        dead = tuple(range(100, 114))
        wall = Wall(
            dead_wall_tiles=dead,
            dora_indicators=tuple(dead[FIRST_DORA_INDEX : FIRST_DORA_INDEX + 3]),
            pending_dora_count=1,
        )
        # 3 revealed + 1 pending + 1 new = 5 = MAX, should succeed
        new_wall = increment_pending_dora(wall)
        assert new_wall.pending_dora_count == 2

        # 3 revealed + 2 pending + 1 new = 6 > MAX, should fail
        with pytest.raises(InvalidActionError, match="Cannot exceed"):
            increment_pending_dora(new_wall)


class TestCollectUraDoraIndicators:
    def test_basic_ura_dora(self):
        """Collects ura dora from eagerly stored ura_dora_indicators."""
        dead = tuple(range(100, 114))
        ura_dora = tuple(dead[URA_DORA_START_INDEX : URA_DORA_START_INDEX + MAX_DORA_INDICATORS])
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
            ura_dora_indicators=ura_dora,
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=False)
        assert ura == [dead[URA_DORA_START_INDEX]]

    def test_with_kan_ura(self):
        """With kan ura, returns one per revealed dora indicator."""
        dead = tuple(range(100, 114))
        ura_dora = tuple(dead[URA_DORA_START_INDEX : URA_DORA_START_INDEX + MAX_DORA_INDICATORS])
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=tuple(dead[FIRST_DORA_INDEX : FIRST_DORA_INDEX + 3]),
            ura_dora_indicators=ura_dora,
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True)
        assert len(ura) == 3
        for i in range(3):
            assert ura[i] == dead[URA_DORA_START_INDEX + i]

    def test_empty_ura_dora_indicators(self):
        """Returns empty list when ura_dora_indicators is empty."""
        wall = Wall(live_tiles=(), dead_wall_tiles=(), dora_indicators=())
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True)
        assert ura == []

    def test_short_ura_dora(self):
        """Handles case where fewer ura dora than dora indicators are available."""
        dead = tuple(range(100, 108))
        ura_dora = (dead[URA_DORA_START_INDEX],)  # only 1 ura dora available
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX], dead[FIRST_DORA_INDEX + 1]),
            ura_dora_indicators=ura_dora,
        )
        ura = collect_ura_dora_indicators(wall, include_kan_ura=True)
        assert len(ura) == 1
        assert ura[0] == dead[URA_DORA_START_INDEX]

    def test_ura_dora_survives_rinshan_draws(self):
        """Ura dora values are correct even after rinshan draws overwrite dead wall positions."""
        dead = tuple(range(100, 114))
        live = tuple(range(50, 70))
        ura_dora = tuple(dead[URA_DORA_START_INDEX : URA_DORA_START_INDEX + MAX_DORA_INDICATORS])
        wall = Wall(
            live_tiles=live,
            dead_wall_tiles=dead,
            dora_indicators=(dead[FIRST_DORA_INDEX],),
            ura_dora_indicators=ura_dora,
        )
        # Perform 4 rinshan draws (overwrites positions 13, 12, 11, 10 in dead wall)
        current_wall = wall
        for _ in range(4):
            current_wall, _ = draw_from_dead_wall(current_wall)
        # Positions 10 and 11 in dead wall are now overwritten with live tiles
        assert current_wall.dead_wall_tiles[10] != dead[10]
        assert current_wall.dead_wall_tiles[11] != dead[11]
        # But the ura dora indicators are preserved from the original values
        assert current_wall.ura_dora_indicators == ura_dora
        # Add kan dora indicators
        current_wall = current_wall.model_copy(
            update={
                "dora_indicators": tuple(dead[FIRST_DORA_INDEX : FIRST_DORA_INDEX + MAX_DORA_INDICATORS]),
            },
        )
        ura = collect_ura_dora_indicators(current_wall, include_kan_ura=True)
        assert len(ura) == MAX_DORA_INDICATORS
        for i in range(MAX_DORA_INDICATORS):
            assert ura[i] == dead[URA_DORA_START_INDEX + i]


class TestComputeWallBreakInfo:
    def test_target_seat_for_dice_sums(self):
        """Verify target seat for representative dice sums with dealer 0."""
        # sum 2 (min), sum 7 (mid), sum 12 (max)
        assert compute_wall_break_info((1, 1), dealer_seat=0).target_seat == 1
        assert compute_wall_break_info((3, 4), dealer_seat=0).target_seat == 2
        assert compute_wall_break_info((6, 6), dealer_seat=0).target_seat == 3

    def test_rotated_dealer(self):
        """dealer_seat != 0 rotates targets correctly."""
        # dealer=1, sum=5 -> target = (1+5-1)%4 = 1 (dealer itself)
        info = compute_wall_break_info((2, 3), dealer_seat=1)
        assert info.target_seat == 1
        # dealer=2, sum=2 -> target = (2+2-1)%4 = 3
        info = compute_wall_break_info((1, 1), dealer_seat=2)
        assert info.target_seat == 3

    def test_break_stack_values(self):
        """Specific break_stack values for known dice+dealer combos."""
        info = compute_wall_break_info((3, 4), dealer_seat=0)
        assert info.break_stack == 44
        info = compute_wall_break_info((1, 1), dealer_seat=0)
        assert info.break_stack == 32
        info = compute_wall_break_info((6, 6), dealer_seat=0)
        assert info.break_stack == 56


class TestSplitWallByDice:
    def test_rejects_wrong_tile_count(self):
        """Raises ValueError when tile count is not 136."""
        with pytest.raises(ValueError, match="Expected 136"):
            _split_wall_by_dice(list(range(100)), (3, 4), dealer_seat=0)

    def test_dead_wall_layout(self):
        """Dead wall tuple has correct layout: indices 0-6 = tops, indices 7-13 = bottoms."""
        tiles = _make_tile_list()
        _live, dead = _split_wall_by_dice(tiles, (3, 4), dealer_seat=0)
        expected_tops = [tiles[s * 2] for s in range(44, 51)]
        expected_bottoms = [tiles[s * 2 + 1] for s in range(44, 51)]
        assert list(dead[:7]) == expected_tops
        assert list(dead[7:]) == expected_bottoms

    def test_live_wall_order(self):
        """Live wall tiles follow dealing order: stack left of break going counter-clockwise."""
        tiles = _make_tile_list()
        live, _ = _split_wall_by_dice(tiles, (3, 4), dealer_seat=0)
        assert live[0] == tiles[43 * 2]  # top of stack 43
        assert live[1] == tiles[43 * 2 + 1]  # bottom of stack 43
        assert live[2] == tiles[42 * 2]  # top of stack 42
        assert live[3] == tiles[42 * 2 + 1]  # bottom of stack 42

    def test_wrapping(self):
        """dice_sum=2 causes dead wall to wrap from one player's segment to next."""
        tiles = _make_tile_list()
        live, dead = _split_wall_by_dice(tiles, (1, 1), dealer_seat=0)
        dead_stacks = [32, 33, 34, 35, 36, 37, 38]
        expected_tops = [tiles[s * 2] for s in dead_stacks]
        assert list(dead[:7]) == expected_tops
        assert live[0] == tiles[31 * 2]

    def test_sizes(self):
        """Live wall always 122, dead wall always 14 regardless of dice."""
        tiles = _make_tile_list()
        for dice in [(1, 1), (3, 4), (6, 6)]:
            live, dead = _split_wall_by_dice(tiles, dice, dealer_seat=0)
            assert len(live) == LIVE_WALL_STACKS * 2
            assert len(dead) == DEAD_WALL_STACKS * 2

    def test_all_tiles_present(self):
        """Union of live + dead wall contains all 136 tile IDs."""
        tiles = _make_tile_list()
        live, dead = _split_wall_by_dice(tiles, (4, 5), dealer_seat=2)
        all_tiles = list(live) + list(dead)
        assert sorted(all_tiles) == list(range(NUM_TILES))
