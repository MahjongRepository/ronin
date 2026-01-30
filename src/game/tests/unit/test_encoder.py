"""
Tests for MessagePack encoder module.
"""

import msgpack
import pytest

from game.messaging.encoder import DecodeError, decode, encode


class TestEncode:
    def test_encode_simple_dict(self) -> None:
        data = {"type": "draw", "seat": 0, "tile": "1m"}
        result = encode(data)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_empty_dict(self) -> None:
        data = {}
        result = encode(data)

        assert isinstance(result, bytes)

    def test_encode_nested_dict(self) -> None:
        data = {
            "type": "round_end",
            "result": {"type": "tsumo", "winner_seat": 0, "hand": {"han": 3, "fu": 30}},
        }
        result = encode(data)

        assert isinstance(result, bytes)

    def test_encode_with_list(self) -> None:
        data = {
            "type": "meld",
            "tile_ids": [10, 11, 12],
            "tiles": ["3m", "3m", "3m"],
        }
        result = encode(data)

        assert isinstance(result, bytes)


class TestDecode:
    def test_decode_simple_dict(self) -> None:
        data = {"type": "draw", "seat": 0, "tile": "1m"}
        encoded = encode(data)

        result = decode(encoded)

        assert result == data

    def test_decode_empty_dict(self) -> None:
        data = {}
        encoded = encode(data)

        result = decode(encoded)

        assert result == data

    def test_decode_nested_dict(self) -> None:
        data = {
            "type": "round_end",
            "result": {"type": "tsumo", "winner_seat": 0, "hand": {"han": 3, "fu": 30}},
        }
        encoded = encode(data)

        result = decode(encoded)

        assert result == data

    def test_decode_with_list(self) -> None:
        data = {
            "type": "meld",
            "tile_ids": [10, 11, 12],
            "tiles": ["3m", "3m", "3m"],
        }
        encoded = encode(data)

        result = decode(encoded)

        assert result == data


class TestRoundTrip:
    def test_round_trip_draw_event(self) -> None:
        data = {"type": "draw", "seat": 0, "tile_id": 42, "tile": "1m", "target": "seat_0"}

        assert decode(encode(data)) == data

    def test_round_trip_discard_event(self) -> None:
        data = {
            "type": "discard",
            "seat": 1,
            "tile_id": 50,
            "tile": "5s",
            "is_tsumogiri": True,
            "is_riichi": False,
            "target": "all",
        }

        assert decode(encode(data)) == data

    def test_round_trip_turn_event(self) -> None:
        data = {
            "type": "turn",
            "current_seat": 2,
            "available_actions": [
                {"action": "discard", "tiles": [10, 20, 30]},
                {"action": "riichi"},
            ],
            "wall_count": 70,
            "target": "seat_2",
        }

        assert decode(encode(data)) == data

    def test_round_trip_call_prompt_event(self) -> None:
        data = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 20,
            "from_seat": 0,
            "callers": [
                {"seat": 1, "call_type": "pon", "tile_34": 5, "priority": 1},
                {"seat": 2, "call_type": "chi", "tile_34": 5, "options": [[4, 8]], "priority": 2},
            ],
            "target": "all",
        }

        assert decode(encode(data)) == data

    def test_round_trip_with_none_values(self) -> None:
        data = {
            "type": "meld",
            "meld_type": "kan",
            "caller_seat": 0,
            "from_seat": None,
            "kan_type": "closed",
            "tile_ids": [36, 37, 38, 39],
            "tiles": ["1p", "1p", "1p", "1p"],
            "target": "all",
        }

        assert decode(encode(data)) == data

    def test_round_trip_with_boolean_values(self) -> None:
        data = {"success": True, "error": False}

        assert decode(encode(data)) == data

    def test_round_trip_with_integer_values(self) -> None:
        data = {"score": 25000, "negative_score": -8000, "zero": 0}

        assert decode(encode(data)) == data


class TestDecodeErrors:
    def test_invalid_msgpack_data_raises_decode_error(self) -> None:
        """Decoding invalid bytes raises DecodeError."""
        with pytest.raises(DecodeError, match="failed to decode"):
            decode(b"\xff\xff\xff")

    def test_non_dict_result_raises_decode_error(self) -> None:
        """Decoding valid msgpack that is not a dict raises DecodeError."""
        data = msgpack.packb([1, 2, 3])

        with pytest.raises(DecodeError, match="expected dict, got list"):
            decode(data)
