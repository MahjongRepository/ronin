from itertools import product

import pytest
from pydantic import ValidationError

from game.logic.rng import SEED_BYTES
from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES
from game.logic.wall import (
    DEAD_WALL_SIZE,
    DEAD_WALL_STACKS,
    MAX_DORA_INDICATORS,
    MAX_RINSHAN_DRAWS,
    STACKS_PER_PLAYER,
    TOTAL_STACKS,
    DeadWall,
    TileStack,
    Wall,
    _split_wall_by_dice,
    add_dora_indicator,
    build_dead_wall,
    clear_pending_dora,
    collect_ura_dora_indicators,
    create_wall,
    create_wall_from_tiles,
    deal_initial_hands,
    draw_from_dead_wall,
    draw_tile,
    increment_pending_dora,
    reveal_pending_dora,
)
from game.tests.helpers.wall import make_wall

FIXED_SEED = "ab" * SEED_BYTES
DICE_PAIRS = [(a, b) for a in range(1, 7) for b in range(1, 7)]


def _stack_index(seat: int, position_from_right: int) -> int:
    return seat * STACKS_PER_PLAYER + STACKS_PER_PLAYER - position_from_right


def _expected_layout(dealer_seat: int, dice: tuple[int, int]) -> tuple[list[int], list[int]]:
    """
    Physical oracle: count the dice sum counter-clockwise from the dealer to pick a wall, count that many stacks from
    its right end, then walk clockwise (left along each wall, then the previous seat's wall from its right end) for the
    61 live stacks; the seven stacks walked last, read back from the break, are the dead wall.
    """
    dice_sum = sum(dice)
    target = (dealer_seat + dice_sum - 1) % NUM_PLAYERS
    walk: list[int] = []
    seat, position = target, dice_sum + 1
    while len(walk) < TOTAL_STACKS:
        if position > STACKS_PER_PLAYER:
            seat, position = (seat - 1) % NUM_PLAYERS, 1

        walk.append(_stack_index(seat, position))
        position += 1

    live_stacks = walk[: TOTAL_STACKS - DEAD_WALL_STACKS]
    dead_stacks = list(reversed(walk[TOTAL_STACKS - DEAD_WALL_STACKS :]))
    return live_stacks, dead_stacks


class TestWallGeometry:
    @pytest.mark.parametrize(("dealer_seat", "dice"), list(product(range(NUM_PLAYERS), DICE_PAIRS)))
    def test_split_wall_by_dice__when_any_dealer_and_dice__should_match_physical_count(self, dealer_seat, dice):
        tiles = list(range(NUM_TILES))

        live_tiles, dead_stacks = _split_wall_by_dice(tiles, dice, dealer_seat)
        expected_live, expected_dead = _expected_layout(dealer_seat, dice)
        assert live_tiles == [t for s in expected_live for t in (2 * s, 2 * s + 1)]
        assert dead_stacks == [TileStack(top=2 * s, bottom=2 * s + 1) for s in expected_dead]

    def test_split_wall_by_dice__when_dice_sum_five_from_dealer_zero__should_break_the_dealers_own_wall(self):
        _live, dead_stacks = _split_wall_by_dice(list(range(NUM_TILES)), (2, 3), 0)
        assert dead_stacks[0].top == 2 * _stack_index(0, 5)
        assert dead_stacks[-1].top == 2 * _stack_index(1, 16)


class TestCreateWall:
    def test_create_wall__when_created__should_partition_all_tiles_with_one_dora_revealed(self):
        wall = create_wall(seed=FIXED_SEED, round_number=0, dealer_seat=0)
        assert len(wall.live_tiles) == NUM_TILES - DEAD_WALL_SIZE
        assert len(wall.dead_wall.tiles) == DEAD_WALL_SIZE
        assert sorted((*wall.live_tiles, *wall.dead_wall.tiles)) == list(range(NUM_TILES))
        assert wall.dora_indicators == (wall.dead_wall.indicators[0].top,)
        assert len(wall.dead_wall.rinshan) == MAX_RINSHAN_DRAWS
        assert wall.dead_wall.reserve == ()

    def test_create_wall__when_same_inputs__should_produce_same_wall(self):
        assert create_wall(seed=FIXED_SEED, round_number=0, dealer_seat=0) == create_wall(
            seed=FIXED_SEED, round_number=0, dealer_seat=0
        )

    def test_create_wall__when_seed_or_round_differ__should_produce_different_walls(self):
        wall = create_wall(seed=FIXED_SEED, round_number=0, dealer_seat=0)
        assert wall.live_tiles != create_wall(seed="cd" * SEED_BYTES, round_number=0, dealer_seat=0).live_tiles
        assert wall.live_tiles != create_wall(seed=FIXED_SEED, round_number=1, dealer_seat=0).live_tiles

    def test_create_wall__when_dealer_seats_differ__should_keep_dice_but_break_elsewhere(self):
        wall0 = create_wall(seed=FIXED_SEED, round_number=0, dealer_seat=0)
        wall1 = create_wall(seed=FIXED_SEED, round_number=0, dealer_seat=1)
        assert wall0.dice == wall1.dice
        assert wall0.live_tiles != wall1.live_tiles


class TestCreateWallFromTiles:
    def test_create_wall_from_tiles__when_given_order__should_lay_out_live_then_dead_stacks(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        assert wall.live_tiles == tuple(range(122))
        assert wall.dead_wall.rinshan == (122, 129, 123, 130)
        assert wall.dead_wall.indicators == tuple(TileStack(top=124 + i, bottom=131 + i) for i in range(5))
        assert wall.dora_indicators == (124,)

    def test_create_wall_from_tiles__when_wrong_tile_count__should_raise(self):
        with pytest.raises(ValueError, match="Expected 136"):
            create_wall_from_tiles(list(range(10)))

    def test_create_wall_from_tiles__when_duplicate_tiles__should_raise(self):
        with pytest.raises(ValueError, match="unique"):
            create_wall_from_tiles([0] * NUM_TILES)

    def test_create_wall_from_tiles__when_tile_id_out_of_range__should_raise(self):
        tiles = list(range(NUM_TILES))
        tiles[0] = 999
        with pytest.raises(ValueError, match="integers in"):
            create_wall_from_tiles(tiles)


class TestDeadWallValidation:
    def test_dead_wall__when_a_tile_appears_twice__should_raise(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        dead = wall.dead_wall
        with pytest.raises(ValidationError, match="distinct"):
            DeadWall(rinshan=(dead.rinshan[0], *dead.rinshan[:3]), indicators=dead.indicators, reserve=())

    def test_dead_wall__when_rinshan_and_reserve_do_not_total_four__should_raise(self):
        dead = create_wall_from_tiles(list(range(NUM_TILES))).dead_wall
        with pytest.raises(ValidationError, match="total 4"):
            DeadWall(rinshan=dead.rinshan[:3], indicators=dead.indicators, reserve=())

    def test_dead_wall__when_indicator_stacks_are_not_five__should_raise(self):
        dead = create_wall_from_tiles(list(range(NUM_TILES))).dead_wall
        with pytest.raises(ValidationError, match="5 indicator stacks"):
            DeadWall(
                rinshan=(*dead.rinshan, dead.indicators[4].top, dead.indicators[4].bottom),
                indicators=dead.indicators[:4],
                reserve=(),
            )

    def test_dead_wall__when_nothing_revealed__should_raise(self):
        dead = create_wall_from_tiles(list(range(NUM_TILES))).dead_wall
        with pytest.raises(ValidationError, match="revealed_count"):
            DeadWall(rinshan=dead.rinshan, indicators=dead.indicators, reserve=(), revealed_count=0)

    def test_build_dead_wall__when_not_seven_stacks__should_raise(self):
        with pytest.raises(ValueError, match="7 dead wall stacks"):
            build_dead_wall([TileStack(top=0, bottom=1)])

    def test_split_wall_by_dice__when_not_136_tiles__should_raise(self):
        with pytest.raises(ValueError, match="Expected 136"):
            _split_wall_by_dice(list(range(10)), (1, 1), 0)

    def test_dead_wall__when_reveals_exceed_indicator_stacks__should_raise(self):
        dead = create_wall_from_tiles(list(range(NUM_TILES))).dead_wall
        with pytest.raises(ValidationError, match="cannot exceed"):
            DeadWall(rinshan=dead.rinshan, indicators=dead.indicators, reserve=(), revealed_count=4, pending_reveals=2)


class TestDealInitialHands:
    def test_deal_initial_hands__when_dealt__should_give_each_seat_13_sorted_unique_tiles(self):
        wall = make_wall(live_tiles=range(122))

        new_wall, hands = deal_initial_hands(wall, dealer_seat=0)
        assert [len(h) for h in hands] == [13] * NUM_PLAYERS
        assert all(h == sorted(h) for h in hands)
        assert len({t for h in hands for t in h}) == 52
        assert len(new_wall.live_tiles) == 122 - 52

    @pytest.mark.parametrize("dealer_seat", [0, 2])
    def test_deal_initial_hands__when_dealt__should_give_dealer_the_first_block(self, dealer_seat):
        wall = make_wall(live_tiles=range(122))

        _new_wall, hands = deal_initial_hands(wall, dealer_seat=dealer_seat)
        assert hands[dealer_seat][:4] == [0, 1, 2, 3]
        assert hands[(dealer_seat + 1) % NUM_PLAYERS][:4] == [4, 5, 6, 7]

    def test_deal_initial_hands__when_live_wall_too_short__should_raise(self):
        with pytest.raises(ValueError, match="need at least"):
            deal_initial_hands(make_wall(live_tiles=range(10)), dealer_seat=0)


class TestDrawTile:
    def test_draw_tile__when_wall_has_tiles__should_draw_from_front(self):
        new_wall, tile = draw_tile(make_wall(live_tiles=(5, 6, 7)))
        assert tile == 5
        assert new_wall.live_tiles == (6, 7)

    def test_draw_tile__when_wall_empty__should_return_none_and_same_wall(self):
        wall = make_wall()
        assert draw_tile(wall) == (wall, None)


class TestDrawFromDeadWall:
    def test_draw_from_dead_wall__when_drawn_four_times__should_take_the_two_break_side_stacks_top_first(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))

        drawn = []
        for _ in range(MAX_RINSHAN_DRAWS):
            wall, tile = draw_from_dead_wall(wall)
            drawn.append(tile)
        assert drawn == [122, 129, 123, 130]
        assert wall.dead_wall.rinshan == ()

    def test_draw_from_dead_wall__when_drawn__should_move_last_live_tile_into_the_reserve(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))

        new_wall, _ = draw_from_dead_wall(wall)
        assert new_wall.dead_wall.reserve == (121,)
        assert new_wall.live_tiles == tuple(range(121))
        assert len(new_wall.dead_wall.tiles) == DEAD_WALL_SIZE

    def test_draw_from_dead_wall__when_live_wall_empty__should_raise(self):
        with pytest.raises(AssertionError, match="live wall is empty"):
            draw_from_dead_wall(make_wall())

    def test_draw_from_dead_wall__when_no_rinshan_left__should_raise(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        for _ in range(MAX_RINSHAN_DRAWS):
            wall, _ = draw_from_dead_wall(wall)

        with pytest.raises(AssertionError, match="No more rinshan"):
            draw_from_dead_wall(wall)


def _check_indicator_integrity(wall: Wall, drawn: list[int]) -> None:
    dead = wall.dead_wall
    assert len(dead.tiles) == DEAD_WALL_SIZE
    assert not set(drawn) & set(dead.tiles)
    assert not set(wall.live_tiles) & set(dead.tiles)
    assert dead.revealed_count + dead.pending_reveals <= MAX_DORA_INDICATORS
    ura = collect_ura_dora_indicators(wall, include_kan_ura=True)
    assert len(ura) == len(wall.dora_indicators)
    for dora, under in zip(wall.dora_indicators, ura, strict=True):
        stack = next(s for s in dead.indicators if s.top == dora)
        assert stack.bottom == under


KAN_SEQUENCES = [
    ["kan_now"] * 4,
    ["kan_later", "reveal"] * 4,
    ["kan_later", "kan_now", "reveal", "kan_later", "kan_later", "reveal"],
    ["kan_later", "clear", "kan_now", "kan_now", "kan_later", "clear"],
    ["kan_later", "kan_later", "kan_later", "kan_later", "reveal"],
]


class TestDoraReveals:
    @pytest.mark.parametrize("sequence", KAN_SEQUENCES, ids="-".join)
    def test_dead_wall__when_kans_and_reveals_interleave__should_keep_indicators_paired_and_out_of_play(self, sequence):
        wall = create_wall(seed=FIXED_SEED, round_number=0, dealer_seat=0)
        original = wall.dead_wall.indicators

        drawn: list[int] = []
        kans = 0
        for step in sequence:
            if step.startswith("kan"):
                wall, tile = draw_from_dead_wall(wall)
                drawn.append(tile)
                kans += 1
                wall = add_dora_indicator(wall)[0] if step == "kan_now" else increment_pending_dora(wall)
            elif step == "reveal":
                wall, _revealed = reveal_pending_dora(wall)
            else:
                wall = clear_pending_dora(wall)

            _check_indicator_integrity(wall, drawn)
            assert wall.dead_wall.indicators == original

        assert len(wall.dead_wall.reserve) == kans

    def test_add_dora_indicator__when_added__should_reveal_successive_indicator_tops(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))

        wall, second = add_dora_indicator(wall)
        wall, third = add_dora_indicator(wall)
        assert (second, third) == (125, 126)
        assert wall.dora_indicators == (124, 125, 126)

    def test_add_dora_indicator__when_all_five_revealed__should_raise(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        for _ in range(MAX_DORA_INDICATORS - 1):
            wall, _ = add_dora_indicator(wall)

        with pytest.raises(AssertionError, match="Cannot add more"):
            add_dora_indicator(wall)

    def test_reveal_pending_dora__when_two_pending__should_reveal_both_in_order_and_clear_pending(self):
        wall = increment_pending_dora(increment_pending_dora(create_wall_from_tiles(list(range(NUM_TILES)))))

        wall, revealed = reveal_pending_dora(wall)
        assert revealed == [125, 126]
        assert wall.pending_dora_count == 0
        assert wall.dora_indicators == (124, 125, 126)

    def test_reveal_pending_dora__when_none_pending__should_return_same_wall(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        assert reveal_pending_dora(wall) == (wall, [])

    def test_increment_pending_dora__when_revealed_plus_pending_would_exceed_five__should_raise(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        for _ in range(2):
            wall, _ = add_dora_indicator(wall)
        for _ in range(2):
            wall = increment_pending_dora(wall)

        with pytest.raises(AssertionError, match="Cannot exceed"):
            increment_pending_dora(wall)

    def test_clear_pending_dora__when_pending__should_drop_them_without_revealing(self):
        wall = increment_pending_dora(create_wall_from_tiles(list(range(NUM_TILES))))

        cleared = clear_pending_dora(wall)
        assert cleared.pending_dora_count == 0
        assert cleared.dora_indicators == (124,)


class TestCollectUraDoraIndicators:
    def test_collect_ura_dora__when_kan_ura_disabled__should_return_only_the_first_ura(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        wall, _ = add_dora_indicator(wall)
        assert collect_ura_dora_indicators(wall, include_kan_ura=False) == [131]

    def test_collect_ura_dora__when_kan_ura_enabled__should_return_one_ura_per_revealed_dora(self):
        wall = create_wall_from_tiles(list(range(NUM_TILES)))
        wall, _ = add_dora_indicator(wall)
        assert collect_ura_dora_indicators(wall, include_kan_ura=True) == [131, 132]
