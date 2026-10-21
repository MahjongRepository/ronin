import pytest

from game.logic.tiles import (
    hand_to_34_array,
    is_honor,
    is_terminal,
    tile_to_34,
)


class TestTileTo34:
    def test_tile_to_34__when_suit_boundary_tiles__should_map_to_suit_indices(self):
        # First and last tile of each suit map to correct 34-format index
        assert tile_to_34(0) == 0  # 1m
        assert tile_to_34(35) == 8  # 9m
        assert tile_to_34(36) == 9  # 1p
        assert tile_to_34(71) == 17  # 9p
        assert tile_to_34(72) == 18  # 1s
        assert tile_to_34(107) == 26  # 9s
        assert tile_to_34(108) == 27  # east
        assert tile_to_34(135) == 33  # chun

    def test_tile_to_34__when_four_copies__should_map_to_same_index(self):
        # All 4 copies of 1m map to the same 34-format index
        assert tile_to_34(0) == tile_to_34(1) == tile_to_34(2) == tile_to_34(3) == 0

    def test_tile_to_34__when_tile_id_out_of_range__should_raise(self):
        with pytest.raises(ValueError, match="tile_id must be in"):
            tile_to_34(-1)
        with pytest.raises(ValueError, match="tile_id must be in"):
            tile_to_34(136)


class TestIsTerminal:
    def test_is_terminal__when_1_or_9_of_a_suit__should_be_true(self):
        # 1 and 9 of each suit
        assert is_terminal(0) is True  # 1m
        assert is_terminal(8) is True  # 9m
        assert is_terminal(9) is True  # 1p
        assert is_terminal(17) is True  # 9p
        assert is_terminal(18) is True  # 1s
        assert is_terminal(26) is True  # 9s

    def test_is_terminal__when_simple_or_honor__should_be_false(self):
        assert is_terminal(4) is False  # 5m (middle tile)
        assert is_terminal(27) is False  # east (honor, not terminal)


class TestIsHonor:
    def test_is_honor__when_wind_or_dragon__should_be_true(self):
        assert is_honor(27) is True  # east
        assert is_honor(30) is True  # north
        assert is_honor(31) is True  # haku
        assert is_honor(33) is True  # chun

    def test_is_honor__when_suit_tile__should_be_false(self):
        assert is_honor(0) is False  # 1m
        assert is_honor(26) is False  # 9s


class TestHandTo34Array:
    def test_hand_to_34_array__when_four_copies__should_count_4_at_one_index(self):
        # 4 copies of 1m (tiles 0-3) all map to index 0
        result = hand_to_34_array([0, 1, 2, 3])
        assert result[0] == 4
        assert sum(result) == 4

    def test_hand_to_34_array__when_mixed_suits__should_count_each_index(self):
        # Tiles from different suits aggregate correctly
        result = hand_to_34_array([0, 36, 108])
        assert result[0] == 1  # 1m
        assert result[9] == 1  # 1p
        assert result[27] == 1  # east

    def test_hand_to_34_array__when_tile_id_out_of_range__should_raise(self):
        with pytest.raises(ValueError, match="tile_id must be in"):
            hand_to_34_array([-1, 0, 4])
        with pytest.raises(ValueError, match="tile_id must be in"):
            hand_to_34_array([0, 4, 136])
