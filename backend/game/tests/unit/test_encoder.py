import json
from pathlib import Path

import msgpack
import pytest

from game.messaging.encoder import MAX_BUFFER_LEN, MAX_NESTING, DecodeError, decode, encode
from game.messaging.types import PONG_PAYLOAD
from game.messaging.wire_enums import WireClientMessageType
from game.wire.keys import LIVE_KEYS, WireKey

_GOLDEN = Path(__file__).parents[1] / "fixtures/live-protocol-golden.json"


def _read_json_payload(value: object, field: int | None = None) -> object:
    if field in (WireKey.SCORES, WireKey.SCORE_CHANGES):
        return value

    if isinstance(value, dict):
        return {int(key): _read_json_payload(item, int(key)) for key, item in value.items()}

    if isinstance(value, list):
        return [_read_json_payload(item) for item in value]

    return value


def test_encode_decode__when_shared_golden_frames__should_pin_integer_keys_and_preserve_numeric_fields():
    golden = json.loads(_GOLDEN.read_text())
    assert golden["named_keys"] == {name: int(key) for name, key in WireKey.__members__.items() if key in LIVE_KEYS}
    for frame in golden["frames"]:
        content = bytes.fromhex(frame["hex"])
        payload = _read_json_payload(frame["payload"])
        assert encode(payload) == content
        assert decode(content) == payload

    frames = {frame["name"]: bytes.fromhex(frame["hex"]) for frame in golden["frames"]}
    assert encode({WireKey.EVENT_TYPE: WireClientMessageType.PING}) == frames["ping"]
    assert encode(PONG_PAYLOAD) == frames["pong"]


def test_encode__when_nested_score_maps__should_preserve_seat_data_keys():
    payload = {
        WireKey.ROUND_RESULT: {
            WireKey.SCORES: {"0": 250, "1": 250, "2": 250, "3": 250},
            WireKey.SCORE_CHANGES: {"0": 10, "1": -10, "2": 0, "3": 0},
        }
    }
    encoded = encode(payload)
    raw = msgpack.unpackb(encoded, strict_map_key=False)
    assert raw == {
        WireKey.ROUND_RESULT: {
            WireKey.SCORES: {"0": 250, "1": 250, "2": 250, "3": 250},
            WireKey.SCORE_CHANGES: {"0": 10, "1": -10, "2": 0, "3": 0},
        },
    }
    assert decode(encoded) == {
        WireKey.ROUND_RESULT: {
            WireKey.SCORES: {"0": 250, "1": 250, "2": 250, "3": 250},
            WireKey.SCORE_CHANGES: {"0": 10, "1": -10, "2": 0, "3": 0},
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": 1},
        {"t": 1},
        {WireKey.GAME_SETTINGS: {}},
        {WireKey.SCORES: []},
        {WireKey.SCORES: {4: 0}},
        {WireKey.SCORES: {0: 0, "0": 1}},
        {WireKey.SCORES: {0: True}},
        {WireKey.SCORES: {False: 0}},
        {WireKey.MY_TILES: {1, 2}},
    ],
)
def test_encode__when_metadata_or_data_keys_invalid__should_refuse(payload):
    with pytest.raises((ValueError, TypeError), match=r"unknown|score|unsupported"):
        encode(payload)


@pytest.mark.parametrize(
    "raw",
    [
        {"t": 1},
        {255: 1},
        {WireKey.EVENT_TYPE: {True: 1}},
        {WireKey.GAME_SETTINGS: {}},
        {WireKey.SCORES: {0: 250}},
        {WireKey.SCORE_CHANGES: {"4": 0}},
        {WireKey.SCORES: {"0": False}},
        {WireKey.SCORES: []},
        {WireKey.PLAYERS: [msgpack.ExtType(1, b"data")]},
    ],
)
def test_decode__when_metadata_or_data_keys_invalid__should_refuse(raw):
    with pytest.raises(DecodeError, match="failed to decode"):
        decode(msgpack.packb(raw))


@pytest.mark.parametrize(
    "content",
    [
        b"\x82" + msgpack.packb(WireKey.EVENT_TYPE) + b"\x01" + msgpack.packb(WireKey.EVENT_TYPE) + b"\x02",
        b"\x81" + msgpack.packb(WireKey.SCORES) + b"\x82\xa10\x01\xa10\x02",
    ],
)
def test_decode__when_duplicate_keys__should_refuse_before_values_are_overwritten(content):
    with pytest.raises(DecodeError, match="unique"):
        decode(content)


def test_encode_decode__when_tuple_and_scalar_fields__should_preserve_values():
    payload = {
        WireKey.CALL_OPTIONS: ((1, 2),),
        WireKey.BANK_SECONDS: 2.5,
        WireKey.FURITEN: False,
        WireKey.ROUND_RESULT: None,
        WireKey.SESSION_ERROR_MESSAGE: b"bytes",
    }
    assert decode(encode(payload)) == {
        WireKey.CALL_OPTIONS: [[1, 2]],
        WireKey.BANK_SECONDS: 2.5,
        WireKey.FURITEN: False,
        WireKey.ROUND_RESULT: None,
        WireKey.SESSION_ERROR_MESSAGE: b"bytes",
    }


def test_encode_decode__when_nesting_limit_exceeded__should_refuse():
    named = {WireKey.EVENT_TYPE: 1}
    numbered = {WireKey.EVENT_TYPE: 1}
    for _ in range(MAX_NESTING + 1):
        named = {WireKey.ROUND_RESULT: named}
        numbered = {WireKey.ROUND_RESULT: numbered}

    with pytest.raises(ValueError, match="nesting"):
        encode(named)

    with pytest.raises(DecodeError, match="nesting"):
        decode(msgpack.packb(numbered))


def test_decode__when_invalid_msgpack__should_raise_decode_error():
    with pytest.raises(DecodeError, match="failed to decode"):
        decode(b"\xff\xff\xff")


def test_decode__when_result_not_dict__should_raise_decode_error():
    with pytest.raises(DecodeError, match="expected dict, got list"):
        decode(msgpack.packb([1, 2, 3]))


def test_decode__when_payload_oversized__should_raise_decode_error():
    with pytest.raises(DecodeError, match="payload too large"):
        decode(b"\x00" * (MAX_BUFFER_LEN + 1))
