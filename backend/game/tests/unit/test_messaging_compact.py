"""Tests for compact draw/discard integer encoding."""

import pytest

from game.messaging.compact import (
    decode_discard,
    decode_draw,
    encode_discard,
    encode_draw,
)


class TestDrawEncoding:
    """Verify draw round-trip encoding and boundary behavior."""

    def test_round_trip_seat_0_tile_0(self):
        d = encode_draw(0, 0)
        assert d == 0
        assert decode_draw(d) == (0, 0)

    def test_round_trip_seat_3_tile_135(self):
        d = encode_draw(3, 135)
        assert d == 543
        assert decode_draw(d) == (3, 135)

    def test_round_trip_all_seats(self):
        for seat in range(4):
            tile_id = 42
            d = encode_draw(seat, tile_id)
            decoded_seat, decoded_tile = decode_draw(d)
            assert decoded_seat == seat
            assert decoded_tile == tile_id

    def test_round_trip_boundary_tiles(self):
        for tile_id in (0, 67, 135):
            d = encode_draw(1, tile_id)
            assert decode_draw(d) == (1, tile_id)

    def test_max_value_is_543(self):
        assert encode_draw(3, 135) == 543

    def test_min_value_is_0(self):
        assert encode_draw(0, 0) == 0

    def test_distinct_values_no_collisions(self):
        """All (seat, tile_id) combinations produce unique packed values."""
        values = set()
        for seat in range(4):
            for tile_id in range(136):
                values.add(encode_draw(seat, tile_id))
        assert len(values) == 4 * 136


class TestDrawValidation:
    """Verify draw functions reject invalid inputs."""

    def test_encode_seat_negative(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_draw(-1, 0)

    def test_encode_seat_too_large(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_draw(4, 0)

    def test_encode_tile_negative(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_draw(0, -1)

    def test_encode_tile_too_large(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_draw(0, 136)

    def test_encode_seat_bool_rejected(self):
        with pytest.raises(TypeError, match="seat must be an integer"):
            encode_draw(True, 0)  # noqa: FBT003

    def test_encode_tile_bool_rejected(self):
        with pytest.raises(TypeError, match="tile_id must be an integer"):
            encode_draw(0, False)  # noqa: FBT003

    def test_encode_seat_non_int_rejected(self):
        with pytest.raises(TypeError, match="seat must be an integer"):
            encode_draw("0", 0)

    def test_decode_negative(self):
        with pytest.raises(ValueError, match="Draw packed value must be 0-543"):
            decode_draw(-1)

    def test_decode_too_large(self):
        with pytest.raises(ValueError, match="Draw packed value must be 0-543"):
            decode_draw(544)

    def test_decode_bool_rejected(self):
        with pytest.raises(TypeError, match="Expected integer"):
            decode_draw(True)  # noqa: FBT003

    def test_decode_non_int_rejected(self):
        with pytest.raises(TypeError, match="Expected integer"):
            decode_draw(1.5)


class TestDiscardEncoding:
    """Verify discard round-trip encoding and flag behavior."""

    def test_round_trip_no_flags(self):
        d = encode_discard(0, 0, is_tsumogiri=False, is_riichi=False)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (0, 0, False, False)

    def test_round_trip_tsumogiri_only(self):
        d = encode_discard(2, 100, is_tsumogiri=True, is_riichi=False)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (2, 100, True, False)

    def test_round_trip_riichi_only(self):
        d = encode_discard(1, 50, is_tsumogiri=False, is_riichi=True)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (1, 50, False, True)

    def test_round_trip_both_flags(self):
        d = encode_discard(3, 135, is_tsumogiri=True, is_riichi=True)
        seat, tile_id, tsumogiri, riichi = decode_discard(d)
        assert (seat, tile_id, tsumogiri, riichi) == (3, 135, True, True)

    def test_min_value_is_0(self):
        assert encode_discard(0, 0, is_tsumogiri=False, is_riichi=False) == 0

    def test_max_value_is_2175(self):
        assert encode_discard(3, 135, is_tsumogiri=True, is_riichi=True) == 2175

    def test_flag_ordering_bit0_tsumogiri_bit1_riichi(self):
        """Bit 0 encodes tsumogiri, bit 1 encodes riichi."""
        base = encode_discard(0, 0, is_tsumogiri=False, is_riichi=False)
        tsumogiri_only = encode_discard(0, 0, is_tsumogiri=True, is_riichi=False)
        riichi_only = encode_discard(0, 0, is_tsumogiri=False, is_riichi=True)
        both = encode_discard(0, 0, is_tsumogiri=True, is_riichi=True)
        # flag=0 -> base, flag=1 -> +544, flag=2 -> +1088, flag=3 -> +1632
        assert tsumogiri_only - base == 544  # flag=1
        assert riichi_only - base == 1088  # flag=2
        assert both - base == 1632  # flag=3

    def test_distinct_values_no_collisions(self):
        """All (seat, tile_id, tsumogiri, riichi) combinations produce unique packed values."""
        values = set()
        for seat in range(4):
            for tile_id in range(136):
                for tsumogiri in (False, True):
                    for riichi in (False, True):
                        values.add(encode_discard(seat, tile_id, is_tsumogiri=tsumogiri, is_riichi=riichi))
        assert len(values) == 4 * 136 * 4


class TestDiscardValidation:
    """Verify discard functions reject invalid inputs."""

    def test_encode_seat_negative(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_discard(-1, 0, is_tsumogiri=False, is_riichi=False)

    def test_encode_seat_too_large(self):
        with pytest.raises(ValueError, match="seat must be 0-3"):
            encode_discard(4, 0, is_tsumogiri=False, is_riichi=False)

    def test_encode_tile_negative(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_discard(0, -1, is_tsumogiri=False, is_riichi=False)

    def test_encode_tile_too_large(self):
        with pytest.raises(ValueError, match="tile_id must be 0-135"):
            encode_discard(0, 136, is_tsumogiri=False, is_riichi=False)

    def test_encode_seat_bool_rejected(self):
        with pytest.raises(TypeError, match="seat must be an integer"):
            encode_discard(True, 0, is_tsumogiri=False, is_riichi=False)  # noqa: FBT003

    def test_encode_tile_bool_rejected(self):
        with pytest.raises(TypeError, match="tile_id must be an integer"):
            encode_discard(0, False, is_tsumogiri=False, is_riichi=False)  # noqa: FBT003

    def test_decode_negative(self):
        with pytest.raises(ValueError, match="Discard packed value must be 0-2175"):
            decode_discard(-1)

    def test_decode_too_large(self):
        with pytest.raises(ValueError, match="Discard packed value must be 0-2175"):
            decode_discard(2176)

    def test_decode_bool_rejected(self):
        with pytest.raises(TypeError, match="Expected integer"):
            decode_discard(False)  # noqa: FBT003

    def test_decode_non_int_rejected(self):
        with pytest.raises(TypeError, match="Expected integer"):
            decode_discard("100")
