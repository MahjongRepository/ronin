import pytest

from game.wire.compact import (
    decode_discard,
    decode_draw,
    encode_discard,
    encode_draw,
)


class TestDrawEncoding:
    def test_draw_encoding__when_seat_0_tile_0__should_round_trip_as_0(self):
        d = encode_draw(0, 0)
        assert d == 0
        assert decode_draw(d) == (0, 0)

    def test_draw_encoding__when_seat_3_tile_135__should_round_trip_as_543(self):
        d = encode_draw(3, 135)
        assert d == 543
        assert decode_draw(d) == (3, 135)

    def test_draw_encoding__when_all_seat_tile_pairs__should_produce_distinct_values(self):
        values = set()
        for seat in range(4):
            for tile_id in range(136):
                values.add(encode_draw(seat, tile_id))
        assert len(values) == 4 * 136


class TestDrawValidation:
    def test_encode_draw__when_seat_negative__should_raise(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_draw(-1, 0)

    def test_encode_draw__when_seat_above_3__should_raise(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_draw(4, 0)

    def test_encode_draw__when_tile_negative__should_raise(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_draw(0, -1)

    def test_encode_draw__when_tile_above_135__should_raise(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_draw(0, 136)

    def test_encode_draw__when_seat_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="seat must be an integer"):
            encode_draw(True, 0)  # noqa: FBT003

    def test_encode_draw__when_tile_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="tile_id must be an integer"):
            encode_draw(0, False)  # noqa: FBT003

    def test_decode_draw__when_value_negative__should_raise(self):
        with pytest.raises(ValueError, match="Draw packed value must be 0-543"):
            decode_draw(-1)

    def test_decode_draw__when_value_above_543__should_raise(self):
        with pytest.raises(ValueError, match="Draw packed value must be 0-543"):
            decode_draw(544)

    def test_decode_draw__when_value_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="Expected integer"):
            decode_draw(True)  # noqa: FBT003


class TestDiscardEncoding:
    def test_discard_encoding__when_no_flags__should_round_trip(self):
        d = encode_discard(0, 0, is_tsumogiri=False, is_riichi=False)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (0, 0, False, False)

    def test_discard_encoding__when_tsumogiri_only__should_round_trip(self):
        d = encode_discard(2, 100, is_tsumogiri=True, is_riichi=False)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (2, 100, True, False)

    def test_discard_encoding__when_riichi_only__should_round_trip(self):
        d = encode_discard(1, 50, is_tsumogiri=False, is_riichi=True)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (1, 50, False, True)

    def test_discard_encoding__when_tsumogiri_and_riichi__should_round_trip(self):
        d = encode_discard(3, 135, is_tsumogiri=True, is_riichi=True)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (3, 135, True, True)

    def test_discard_encoding__when_flags_set__should_use_bit0_for_tsumogiri_and_bit1_for_riichi(self):
        base = encode_discard(0, 0, is_tsumogiri=False, is_riichi=False)
        tsumogiri_only = encode_discard(0, 0, is_tsumogiri=True, is_riichi=False)
        riichi_only = encode_discard(0, 0, is_tsumogiri=False, is_riichi=True)
        both = encode_discard(0, 0, is_tsumogiri=True, is_riichi=True)
        # flag=0 -> base, flag=1 -> +544, flag=2 -> +1088, flag=3 -> +1632
        assert tsumogiri_only - base == 544  # flag=1
        assert riichi_only - base == 1088  # flag=2
        assert both - base == 1632  # flag=3

    def test_discard_encoding__when_all_seat_tile_flag_combinations__should_produce_distinct_values(self):
        values = set()
        for seat in range(4):
            for tile_id in range(136):
                for tsumogiri in (False, True):
                    for riichi in (False, True):
                        values.add(encode_discard(seat, tile_id, is_tsumogiri=tsumogiri, is_riichi=riichi))
        assert len(values) == 4 * 136 * 4


class TestDiscardValidation:
    def test_encode_discard__when_seat_negative__should_raise(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_discard(-1, 0, is_tsumogiri=False, is_riichi=False)

    def test_encode_discard__when_seat_above_3__should_raise(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_discard(4, 0, is_tsumogiri=False, is_riichi=False)

    def test_encode_discard__when_tile_negative__should_raise(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_discard(0, -1, is_tsumogiri=False, is_riichi=False)

    def test_encode_discard__when_tile_above_135__should_raise(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_discard(0, 136, is_tsumogiri=False, is_riichi=False)

    def test_encode_discard__when_seat_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="seat must be an integer"):
            encode_discard(True, 0, is_tsumogiri=False, is_riichi=False)  # noqa: FBT003

    def test_encode_discard__when_tile_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="tile_id must be an integer"):
            encode_discard(0, False, is_tsumogiri=False, is_riichi=False)  # noqa: FBT003

    def test_decode_discard__when_value_negative__should_raise(self):
        with pytest.raises(ValueError, match="Discard packed value must be 0-2175"):
            decode_discard(-1)

    def test_decode_discard__when_value_above_2175__should_raise(self):
        with pytest.raises(ValueError, match="Discard packed value must be 0-2175"):
            decode_discard(2176)

    def test_decode_discard__when_value_is_bool__should_raise(self):
        with pytest.raises(TypeError, match="Expected integer"):
            decode_discard(False)  # noqa: FBT003
