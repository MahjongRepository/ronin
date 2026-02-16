"""
MessagePack encoder/decoder for wire format communication.

Provides functions to encode Python dicts to MessagePack bytes and decode
MessagePack bytes back to dicts. Used for binary protocol communication.
"""

from typing import Any

import msgpack


def _stringify_keys(obj: object) -> object:
    """
    Recursively convert integer dict keys to strings.

    MessagePack strict mode only allows string keys, but Pydantic model_dump()
    preserves integer keys from fields like dict[int, int].
    """
    if isinstance(obj, dict):
        return {str(k) if isinstance(k, int) else k: _stringify_keys(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_stringify_keys(item) for item in obj]
    return obj


def encode(data: dict[str, Any]) -> bytes:
    """
    Encode a dict to MessagePack bytes.
    """
    return msgpack.packb(_stringify_keys(data))


class DecodeError(Exception):
    """Error raised when MessagePack decoding fails."""


# Size limits to prevent resource exhaustion from malicious payloads.
MAX_BUFFER_LEN = 256 * 1024  # 256KB total payload
MAX_STR_LEN = 64 * 1024  # 64KB per string
MAX_BIN_LEN = 64 * 1024  # 64KB per binary
MAX_ARRAY_LEN = 1024  # max array elements
MAX_MAP_LEN = 256  # max map entries
MAX_EXT_LEN = 1024  # max extension data


def decode(data: bytes) -> dict[str, Any]:
    """
    Decode MessagePack bytes to a dict.

    Raises DecodeError if data is invalid, not a dict, or exceeds size limits.
    """
    if len(data) > MAX_BUFFER_LEN:
        raise DecodeError(f"payload too large: {len(data)} bytes (max {MAX_BUFFER_LEN})")
    try:
        result = msgpack.unpackb(
            data,
            raw=False,
            max_str_len=MAX_STR_LEN,
            max_bin_len=MAX_BIN_LEN,
            max_array_len=MAX_ARRAY_LEN,
            max_map_len=MAX_MAP_LEN,
            max_ext_len=MAX_EXT_LEN,
        )
    except (msgpack.UnpackException, ValueError) as e:
        raise DecodeError(f"failed to decode MessagePack data: {e}") from e

    if not isinstance(result, dict):
        raise DecodeError(f"expected dict, got {type(result).__name__}")

    return result
