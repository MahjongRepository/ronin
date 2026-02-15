"""
Unit tests for tile representation utilities.

Covers pure function boundary tests for tile_to_34 conversion, is_terminal/is_honor
classification — not achievable via replays.
"""

from game.logic.tiles import (
    is_honor,
    is_terminal,
    tile_to_34,
)


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
