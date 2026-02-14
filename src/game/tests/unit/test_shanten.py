"""Unit tests for shanten calculation module."""

from mahjong.tile import TilesConverter

from game.logic.shanten import (
    _NOT_TENPAI,
    AGARI_STATE,
    calculate_shanten,
)


def _hand(sou="", pin="", man="", honors="") -> list[int]:
    """Convert string notation to 34-element tile array."""
    return TilesConverter.to_34_array(
        TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)
    )


def test_agari_state_constant():
    assert AGARI_STATE == -1


class TestCalculateShanten:
    """Test shanten calculation across all hand patterns."""

    def test_complete_hand(self):
        tiles = _hand(man="123456789", pin="11", sou="234")
        assert calculate_shanten(tiles) == AGARI_STATE

    def test_tenpai(self):
        tiles = _hand(man="123456789", pin="1", sou="234")
        assert calculate_shanten(tiles) == 0

    def test_one_shanten(self):
        tiles = _hand(man="123456789", pin="13", sou="24")
        assert calculate_shanten(tiles) == 1

    def test_chiitoitsu_tenpai(self):
        """Detect tenpai for seven pairs."""
        tiles = _hand(man="1199", pin="1199", sou="1199", honors="1")
        assert calculate_shanten(tiles) == 0

    def test_kokushi_tenpai(self):
        """Detect tenpai for thirteen orphans."""
        tiles = _hand(man="19", pin="19", sou="19", honors="1234567")
        assert calculate_shanten(tiles) == 0

    def test_open_hand_tenpai(self):
        """Tenpai with reduced tile count (simulating open melds)."""
        # 10 tiles = 3*3+1, simulating one open meld
        tiles = _hand(man="123456", pin="1", sou="234")
        assert calculate_shanten(tiles) == 0

    def test_small_open_hand(self):
        """4 tiles = 3*1+1, simulating three open melds."""
        tiles = _hand(man="12", pin="11")
        assert calculate_shanten(tiles) >= 0

    def test_empty_hand_returns_not_tenpai(self):
        tiles = [0] * 34
        assert calculate_shanten(tiles) == _NOT_TENPAI

    def test_invalid_tile_count_returns_not_tenpai(self):
        """3n+0 tile counts are invalid for xiangting."""
        tiles = _hand(man="123")  # 3 tiles
        assert calculate_shanten(tiles) == _NOT_TENPAI
