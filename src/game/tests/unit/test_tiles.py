"""
Unit tests for tile representation utilities.
"""

from mahjong.tile import TilesConverter

from game.logic.tiles import (
    CHUN_34,
    DRAGONS_34,
    EAST_34,
    HAKU_34,
    HATSU_34,
    HONOR_34_END,
    HONOR_34_START,
    MAN_34_END,
    MAN_34_START,
    NORTH_34,
    PIN_34_END,
    PIN_34_START,
    SOU_34_END,
    SOU_34_START,
    SOUTH_34,
    TERMINALS_34,
    WEST_34,
    WINDS_34,
    generate_wall,
    is_honor,
    is_terminal,
    is_terminal_or_honor,
    sort_tiles,
    tile_to_34,
)


class TestTileConstants:
    def test_tile_34_ranges_are_contiguous(self):
        # man: 0-8, pin: 9-17, sou: 18-26, honors: 27-33
        assert MAN_34_START == 0
        assert MAN_34_END == 8
        assert PIN_34_START == 9
        assert PIN_34_END == 17
        assert SOU_34_START == 18
        assert SOU_34_END == 26
        assert HONOR_34_START == 27
        assert HONOR_34_END == 33

    def test_wind_constants(self):
        assert EAST_34 == 27
        assert SOUTH_34 == 28
        assert WEST_34 == 29
        assert NORTH_34 == 30
        assert WINDS_34 == [27, 28, 29, 30]

    def test_dragon_constants(self):
        assert HAKU_34 == 31
        assert HATSU_34 == 32
        assert CHUN_34 == 33
        assert DRAGONS_34 == [31, 32, 33]

    def test_terminal_constants(self):
        # terminals are 1 and 9 of each suit
        assert TERMINALS_34 == [0, 8, 9, 17, 18, 26]


class TestTileTo34:
    def test_converts_man_tiles(self):
        # 1m tiles: 0, 1, 2, 3 all map to 0
        assert tile_to_34(0) == 0
        assert tile_to_34(1) == 0
        assert tile_to_34(2) == 0
        assert tile_to_34(3) == 0
        # 9m tiles: 32, 33, 34, 35 all map to 8
        assert tile_to_34(32) == 8
        assert tile_to_34(35) == 8

    def test_converts_pin_tiles(self):
        # 1p tiles: 36, 37, 38, 39 map to 9
        assert tile_to_34(36) == 9
        assert tile_to_34(39) == 9
        # 9p tiles: 68, 69, 70, 71 map to 17
        assert tile_to_34(68) == 17
        assert tile_to_34(71) == 17

    def test_converts_sou_tiles(self):
        # 1s tiles: 72, 73, 74, 75 map to 18
        assert tile_to_34(72) == 18
        assert tile_to_34(75) == 18
        # 9s tiles: 104, 105, 106, 107 map to 26
        assert tile_to_34(104) == 26
        assert tile_to_34(107) == 26

    def test_converts_honor_tiles(self):
        # east: 108-111 map to 27
        assert tile_to_34(108) == 27
        assert tile_to_34(111) == 27
        # chun (red dragon): 132-135 map to 33
        assert tile_to_34(132) == 33
        assert tile_to_34(135) == 33


class TestIsTerminal:
    def test_terminal_tiles(self):
        # 1m, 9m
        assert is_terminal(0) is True
        assert is_terminal(8) is True
        # 1p, 9p
        assert is_terminal(9) is True
        assert is_terminal(17) is True
        # 1s, 9s
        assert is_terminal(18) is True
        assert is_terminal(26) is True

    def test_non_terminal_tiles(self):
        # middle man tiles
        assert is_terminal(4) is False  # 5m
        # middle pin tiles
        assert is_terminal(13) is False  # 5p
        # honors are not terminals
        assert is_terminal(27) is False  # east


class TestIsHonor:
    def test_honor_tiles(self):
        # winds
        assert is_honor(27) is True  # east
        assert is_honor(30) is True  # north
        # dragons
        assert is_honor(31) is True  # haku
        assert is_honor(33) is True  # chun

    def test_non_honor_tiles(self):
        assert is_honor(0) is False  # 1m
        assert is_honor(17) is False  # 9p
        assert is_honor(26) is False  # 9s


class TestIsTerminalOrHonor:
    def test_terminal_tiles(self):
        assert is_terminal_or_honor(0) is True  # 1m
        assert is_terminal_or_honor(8) is True  # 9m

    def test_honor_tiles(self):
        assert is_terminal_or_honor(27) is True  # east
        assert is_terminal_or_honor(33) is True  # chun

    def test_simple_tiles(self):
        assert is_terminal_or_honor(4) is False  # 5m
        assert is_terminal_or_honor(13) is False  # 5p


class TestGenerateWall:
    def test_wall_has_136_tiles(self):
        wall = generate_wall(0.5, 0)
        assert len(wall) == 136

    def test_wall_contains_all_tiles(self):
        wall = generate_wall(0.5, 0)
        assert sorted(wall) == list(range(136))

    def test_same_seed_and_round_produces_same_wall(self):
        wall1 = generate_wall(0.5, 0)
        wall2 = generate_wall(0.5, 0)
        assert wall1 == wall2

    def test_different_rounds_produce_different_walls(self):
        wall1 = generate_wall(0.5, 0)
        wall2 = generate_wall(0.5, 1)
        assert wall1 != wall2

    def test_different_seeds_produce_different_walls(self):
        wall1 = generate_wall(0.5, 0)
        wall2 = generate_wall(0.6, 0)
        assert wall1 != wall2


class TestSortTiles:
    def test_empty_list(self):
        assert sort_tiles([]) == []

    def test_already_sorted(self):
        tiles = TilesConverter.string_to_136_array(man="123")
        assert sort_tiles(tiles) == TilesConverter.string_to_136_array(man="123")

    def test_unsorted_tiles(self):
        sou = TilesConverter.string_to_136_array(sou="1")
        pin = TilesConverter.string_to_136_array(pin="1")
        man = TilesConverter.string_to_136_array(man="1")
        tiles = [*sou, *pin, *man]
        assert sort_tiles(tiles) == TilesConverter.string_to_136_array(man="1", pin="1", sou="1")

    def test_same_type_different_copies(self):
        # different copies of 1m
        tiles = [3, 1, 2, 0]
        assert sort_tiles(tiles) == [0, 1, 2, 3]
