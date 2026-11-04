from __future__ import annotations

from typing import TYPE_CHECKING

import msgpack
from pydantic import BaseModel, ConfigDict, JsonValue

from game.logic.exceptions import UnsupportedSettingsError
from game.logic.rule_profiles import STANDARD_RULE_PROFILE, get_rule_profile, resolve_rule_profile
from game.logic.settings import GameSettings, validate_settings
from game.wire.enums import WireEventType
from game.wire.keys import REPLAY_KEYS, WireKey
from game.wire.replay_schema import ReplayLineType, validate_replay_event

if TYPE_CHECKING:
    from collections.abc import Sequence

REPLAY_VERSION = "0.4-dev"
REPLAY_SEED_BYTES = 96
MAX_REPLAY_BYTES = 16 * 1024 * 1024
_SCORE_MAP_KEYS = frozenset({WireKey.SCORES, WireKey.SCORE_CHANGES})


if {int(line_type) for line_type in ReplayLineType} & {int(event_type) for event_type in WireEventType}:
    raise RuntimeError(  # pragma: no cover (exhaustive)
        f"ReplayLineType values {list(ReplayLineType)} overlap WireEventType values {list(WireEventType)}",
    )


class ReplaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    id: int
    overrides: dict[str, JsonValue]


def encode_replay_settings(settings: GameSettings, profile_id: int = STANDARD_RULE_PROFILE.id) -> dict[str, object]:
    validate_settings(settings)
    profile = get_rule_profile(profile_id)

    baseline = profile.settings.model_dump(mode="json")
    effective = settings.model_dump(mode="json")
    overrides = {name: value for name, value in effective.items() if value != baseline[name]}
    return {"id": profile.id, "overrides": overrides}


def decode_replay_settings(raw: object) -> GameSettings:
    reference = ReplaySettings.model_validate(raw)
    return resolve_rule_profile(reference.id, reference.overrides)


def _encode_seed(value: object) -> bytes:
    if not isinstance(value, str) or len(value) != REPLAY_SEED_BYTES * 2:
        raise ValueError(f"seed must contain {REPLAY_SEED_BYTES * 2} hexadecimal characters")

    seed = bytes.fromhex(value)
    if len(seed) != REPLAY_SEED_BYTES:
        raise ValueError(f"seed must encode exactly {REPLAY_SEED_BYTES} bytes")

    return seed


def _decode_seed(value: object) -> str:
    if not isinstance(value, bytes) or len(value) != REPLAY_SEED_BYTES:
        raise ValueError(f"seed must be a binary value of {REPLAY_SEED_BYTES} bytes")

    return value.hex()


def _copy_score_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise TypeError("score map must be an object")

    if any(key not in {"0", "1", "2", "3"} or type(score) is not int for key, score in value.items()):
        raise ValueError("score maps require string seat keys and integer scores")

    return dict(value)


def _encode_score_map(value: dict[object, object]) -> dict[str, int]:
    normalized = {str(key): score for key, score in value.items()}
    if len(normalized) != len(value):
        raise ValueError("score map has duplicate seats")

    return _copy_score_map(normalized)


def _encode_value(value: object, field: int | None = None) -> object:
    if field == WireKey.SEED:
        return _encode_seed(value)

    if field == WireKey.GAME_SETTINGS:
        decode_replay_settings(value)
        return value

    if field in _SCORE_MAP_KEYS and isinstance(value, dict):
        return _encode_score_map(value)

    if isinstance(value, dict):
        encoded: dict[int, object] = {}
        for key, item in value.items():
            if not isinstance(key, int) or isinstance(key, bool) or key not in REPLAY_KEYS:
                raise ValueError(f"unknown replay metadata key: {key!r}")

            encoded[key] = _encode_value(item, key)

        return encoded

    if isinstance(value, list | tuple):
        return [_encode_value(item) for item in value]

    return value


def _decode_value(value: object, field: int | None = None) -> object:
    if field == WireKey.SEED:
        return _decode_seed(value)

    if field == WireKey.GAME_SETTINGS:
        decode_replay_settings(value)
        return value

    if field in _SCORE_MAP_KEYS:
        return _copy_score_map(value)

    if isinstance(value, dict):
        decoded: dict[int, object] = {}
        for key, item in value.items():
            if type(key) is not int or key not in REPLAY_KEYS:
                raise ValueError(f"unknown replay metadata key: {key!r}")

            decoded[key] = _decode_value(item, key)

        return decoded

    if isinstance(value, list):
        return [_decode_value(item) for item in value]

    if value is None or isinstance(value, str | bool | int):
        return value

    raise ValueError(f"unsupported replay value: {type(value).__name__}")


def _decode_unique_map(pairs: list[tuple[object, object]]) -> dict[object, object]:
    result: dict[object, object] = {}
    for key, value in pairs:
        if not isinstance(key, str | int) or isinstance(key, bool) or key in result:
            raise ValueError("replay maps require unique string or integer keys")

        result[key] = value

    return result


def _validate_record(record: object, position: int) -> dict[int, object]:
    if not isinstance(record, dict):
        raise TypeError("replay record must be an object")

    if position == 1:
        if record != {WireKey.REPLAY_VERSION: REPLAY_VERSION}:
            raise ValueError(f"unsupported replay version: {record.get(WireKey.REPLAY_VERSION)!r}")

        return record

    validate_replay_event(record)
    return record


def encode_replay_records(records: Sequence[dict[int, object]]) -> bytes:
    if not records:
        raise ValueError("replay is missing its version record")

    return b"".join(
        msgpack.packb(_encode_value(_validate_record(record, position)), use_bin_type=True)
        for position, record in enumerate(records, start=1)
    )


def decode_replay_records(content: bytes) -> list[dict[int, object]]:
    if len(content) > MAX_REPLAY_BYTES:
        raise ValueError(f"replay exceeds {MAX_REPLAY_BYTES} bytes")

    unpacker = msgpack.Unpacker(
        raw=False,
        strict_map_key=False,
        object_pairs_hook=_decode_unique_map,
        max_buffer_size=MAX_REPLAY_BYTES,
        max_str_len=4096,
        max_array_len=4096,
        max_map_len=128,
        max_bin_len=REPLAY_SEED_BYTES,
    )
    unpacker.feed(content)
    records: list[dict[int, object]] = []
    complete_position = 0
    try:
        for raw in unpacker:
            record = _validate_record(_decode_value(raw), len(records) + 1)
            records.append(record)
            complete_position = unpacker.tell()
    except (ValueError, TypeError, UnsupportedSettingsError, msgpack.UnpackException) as error:
        raise ValueError(f"replay record {len(records) + 1} at byte {complete_position}: {error}") from error

    if complete_position != len(content):
        raise ValueError(f"incomplete replay record {len(records) + 1} at byte {complete_position}")

    if not records:
        raise ValueError("replay is missing its version record")

    return records
