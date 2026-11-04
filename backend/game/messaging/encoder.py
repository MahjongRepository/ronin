from __future__ import annotations

from typing import Any

import msgpack

from game.wire.keys import LIVE_KEYS, WireKey

MAX_BUFFER_LEN = 256 * 1024
MAX_STR_LEN = 64 * 1024
MAX_BIN_LEN = 64 * 1024
MAX_ARRAY_LEN = 1024
MAX_MAP_LEN = 256
MAX_EXT_LEN = 1024
MAX_NESTING = 32

_SCORE_MAP_KEYS = frozenset({WireKey.SCORES, WireKey.SCORE_CHANGES})
_SCORE_SEATS = frozenset({"0", "1", "2", "3"})


class DecodeError(Exception):
    """
    Report malformed or oversized binary game messages.
    """


def encode(data: dict[int, Any]) -> bytes:
    """
    Encode a numeric-key protocol message as MessagePack.
    """
    _validate_value(data)
    return msgpack.packb(data, use_bin_type=True)


def _decode_unique_map(pairs: list[tuple[object, object]]) -> dict[object, object]:
    result: dict[object, object] = {}
    for key, value in pairs:
        if type(key) not in (int, str) or key in result:
            raise ValueError("message maps require unique integer or string keys")

        result[key] = value

    return result


def _validate_scores(value: object) -> None:
    if not isinstance(value, dict):
        raise TypeError("score map must be an object")

    if any(
        type(seat) is not str or seat not in _SCORE_SEATS or type(score) is not int for seat, score in value.items()
    ):
        raise ValueError("score map requires string seat keys and integer values")


def _validate_value(value: object, field: int | None = None, depth: int = 0) -> None:
    if depth > MAX_NESTING:
        raise ValueError("message nesting limit exceeded")

    if field in _SCORE_MAP_KEYS:
        _validate_scores(value)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, bool) or not isinstance(key, int) or key not in LIVE_KEYS:
                raise ValueError(f"unknown message metadata key: {key!r}")

            _validate_value(item, key, depth + 1)

        return

    if isinstance(value, list | tuple) and not isinstance(value, msgpack.ExtType):
        for item in value:
            _validate_value(item, depth=depth + 1)

        return

    if value is None or isinstance(value, str | bytes | bool | int | float):
        return

    raise ValueError(f"unsupported message value: {type(value).__name__}")


def decode(data: bytes) -> dict[int, Any]:
    """
    Decode and validate a numeric-key protocol message before routing.
    """
    if len(data) > MAX_BUFFER_LEN:
        raise DecodeError(f"payload too large: {len(data)} bytes (max {MAX_BUFFER_LEN})")

    try:
        raw = msgpack.unpackb(
            data,
            raw=False,
            strict_map_key=False,
            object_pairs_hook=_decode_unique_map,
            max_str_len=MAX_STR_LEN,
            max_bin_len=MAX_BIN_LEN,
            max_array_len=MAX_ARRAY_LEN,
            max_map_len=MAX_MAP_LEN,
            max_ext_len=MAX_EXT_LEN,
        )
        _validate_value(raw)
    except (msgpack.UnpackException, ValueError, TypeError, RecursionError) as error:
        raise DecodeError(f"failed to decode MessagePack data: {error}") from error

    if not isinstance(raw, dict):
        raise DecodeError(f"expected dict, got {type(raw).__name__}")

    return raw
