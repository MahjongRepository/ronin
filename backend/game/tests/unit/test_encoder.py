import msgpack
import pytest

from game.logic.enums import CallType, MeldCallType, MeldViewType
from game.logic.events import EventType
from game.messaging.encoder import MAX_BUFFER_LEN, DecodeError, decode, encode


class TestRoundTrip:
    def test_encode_decode__when_simple_event__should_round_trip(self) -> None:
        data = {"type": EventType.DRAW, "seat": 0, "tile_id": 42, "target": "seat_0"}

        assert decode(encode(data)) == data

    def test_encode_decode__when_call_prompt_event__should_round_trip(self) -> None:
        data = {
            "type": EventType.CALL_PROMPT,
            "call_type": CallType.MELD,
            "tile_id": 20,
            "from_seat": 0,
            "callers": [
                {"seat": 1, "call_type": MeldCallType.PON},
                {"seat": 2, "call_type": MeldCallType.CHI, "options": [[4, 8]]},
            ],
            "target": "all",
        }

        assert decode(encode(data)) == data

    def test_encode_decode__when_none_values__should_round_trip(self) -> None:
        data = {
            "type": EventType.MELD,
            "meld_type": MeldViewType.CLOSED_KAN,
            "caller_seat": 0,
            "from_seat": None,
            "tile_ids": [36, 37, 38, 39],
            "target": "all",
        }

        assert decode(encode(data)) == data


class TestIntegerKeyConversion:
    def test_encode__when_integer_keys__should_convert_to_strings(self) -> None:
        data = {
            "type": "round_result",
            "score_changes": {0: -1000, 1: 0, 2: 0, 3: 1000},
        }
        result = decode(encode(data))

        assert result == {
            "type": "round_result",
            "score_changes": {"0": -1000, "1": 0, "2": 0, "3": 1000},
        }

    def test_encode__when_nested_integer_keys__should_convert_to_strings(self) -> None:
        data = {
            "result": {
                "score_changes": {0: 8000, 1: -8000, 2: 0, 3: 0},
            },
        }
        result = decode(encode(data))

        assert result == {
            "result": {
                "score_changes": {"0": 8000, "1": -8000, "2": 0, "3": 0},
            },
        }

    def test_encode__when_integer_keys_inside_list__should_convert_to_strings(self) -> None:
        data = {
            "results": [{0: 100, 1: -100}],
        }
        result = decode(encode(data))

        assert result == {
            "results": [{"0": 100, "1": -100}],
        }


class TestDecodeErrors:
    def test_decode__when_invalid_msgpack__should_raise_decode_error(self) -> None:
        with pytest.raises(DecodeError, match="failed to decode"):
            decode(b"\xff\xff\xff")

    def test_decode__when_result_not_dict__should_raise_decode_error(self) -> None:
        data = msgpack.packb([1, 2, 3])

        with pytest.raises(DecodeError, match="expected dict, got list"):
            decode(data)

    def test_decode__when_payload_oversized__should_raise_decode_error(self) -> None:
        oversized = b"\x00" * (MAX_BUFFER_LEN + 1)

        with pytest.raises(DecodeError, match="payload too large"):
            decode(oversized)

    def test_decode__when_payload_at_limit__should_accept(self) -> None:
        data = msgpack.packb({"key": "x" * 100})
        assert len(data) <= MAX_BUFFER_LEN
        result = decode(data)
        assert result["key"] == "x" * 100
