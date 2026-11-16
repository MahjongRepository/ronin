import logging

from mahjong.tile import TilesConverter

from game.logic.shanten import (
    _NOT_TENPAI,
    AGARI_STATE,
    calculate_shanten,
)


def _hand(sou="", pin="", man="", honors="") -> list[int]:
    return TilesConverter.to_34_array(
        TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors),
    )


class TestCalculateShanten:
    def test_calculate_shanten__when_hand_complete__should_return_agari_state(self):
        tiles = _hand(man="123456789", pin="11", sou="234")
        assert calculate_shanten(tiles) == AGARI_STATE

    def test_calculate_shanten__when_regular_tenpai__should_return_0(self):
        tiles = _hand(man="123456789", pin="1", sou="234")
        assert calculate_shanten(tiles) == 0

    def test_calculate_shanten__when_one_tile_from_tenpai__should_return_1(self):
        tiles = _hand(man="123456789", pin="13", sou="24")
        assert calculate_shanten(tiles) == 1

    def test_calculate_shanten__when_chiitoitsu_tenpai__should_return_0(self):
        tiles = _hand(man="1199", pin="1199", sou="1199", honors="1")
        assert calculate_shanten(tiles) == 0

    def test_calculate_shanten__when_kokushi_tenpai__should_return_0(self):
        tiles = _hand(man="19", pin="19", sou="19", honors="1234567")
        assert calculate_shanten(tiles) == 0

    def test_calculate_shanten__when_hand_has_fewer_tiles_after_meld__should_return_0(self):
        tiles = _hand(man="123456", pin="1", sou="234")
        assert calculate_shanten(tiles) == 0

    def test_calculate_shanten__when_hand_empty__should_return_not_tenpai_without_warning(self, caplog):
        tiles = [0] * 34
        with caplog.at_level(logging.WARNING, logger="game.logic.shanten"):
            assert calculate_shanten(tiles) == _NOT_TENPAI
        assert caplog.text == ""

    def test_calculate_shanten__when_tile_count_invalid__should_return_not_tenpai_and_warn(self, caplog):
        tiles = _hand(man="123")  # 3 tiles
        with caplog.at_level(logging.WARNING, logger="game.logic.shanten"):
            result = calculate_shanten(tiles)
        assert result == _NOT_TENPAI
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        assert warning_records[0].msg["event"] == "unexpected tile count in shanten calculation"
        assert warning_records[0].msg["tile_count"] == 3
