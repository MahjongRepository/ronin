import hashlib
import json
from pathlib import Path

import msgpack
import pytest

from game.logic.exceptions import UnsupportedSettingsError
from game.logic.rule_profiles import STANDARD_RULE_PROFILE, RuleProfile
from game.logic.settings import GameSettings
from game.wire.keys import REPLAY_KEYS, WireKey
from game.wire.replay_format import (
    MAX_REPLAY_BYTES,
    REPLAY_VERSION,
    decode_replay_records,
    decode_replay_settings,
    encode_replay_records,
    encode_replay_settings,
)

_GOLDEN = Path(__file__).parents[1] / "fixtures" / "replay-format-golden.json"


def _numeric_records(value, field=None):
    if field in {WireKey.GAME_SETTINGS, WireKey.SCORES, WireKey.SCORE_CHANGES}:
        return value

    if isinstance(value, dict):
        return {int(key): _numeric_records(item, int(key)) for key, item in value.items()}

    if isinstance(value, list):
        return [_numeric_records(item) for item in value]

    return value


@pytest.fixture
def golden():
    golden = json.loads(_GOLDEN.read_text())
    golden["records"] = _numeric_records(golden["records"])
    return golden


def _pack(records: list[object]) -> bytes:
    return b"".join(msgpack.packb(record, use_bin_type=True) for record in records)


def test_replay_records__when_shared_golden__should_preserve_records_and_binary_layout(golden):
    encoded = encode_replay_records(golden["records"])
    assert encoded.hex() == golden["hex"]
    assert golden["named_keys"] == {name: key.value for name, key in WireKey.__members__.items() if key in REPLAY_KEYS}
    assert decode_replay_records(encoded) == golden["records"]
    unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
    unpacker.feed(encoded)
    raw = list(unpacker)
    assert raw[1][WireKey.SEED] == bytes(range(96))
    assert raw[1][WireKey.GAME_SETTINGS] == {
        "id": 1,
        "overrides": {"has_akadora": False, "riichi_stick_value": 0},
    }
    assert raw[2][WireKey.DORA_INDICATORS] == [31]
    assert raw[3][WireKey.SCORE_CHANGES] == {"0": 30, "1": -10, "2": -10, "3": -10}


def test_replay_records__when_score_maps_have_domain_seats__should_normalize_only_data_keys(golden):
    record = {**golden["records"][3], WireKey.SCORE_CHANGES: {0: 30, 1: -10, 2: -10, 3: -10}}
    content = encode_replay_records([golden["records"][0], record])
    assert decode_replay_records(content)[1] == golden["records"][3]


@pytest.mark.parametrize("seed", ["ff", "g" * 192, " " * 192, b"x" * 96])
def test_replay_records__when_seed_is_not_full_hex__should_reject(seed, golden):
    records = [golden["records"][0], {**golden["records"][1], WireKey.SEED: seed}]
    with pytest.raises(ValueError, match=r"seed|hexadecimal|replay field 54"):
        encode_replay_records(records)


@pytest.mark.parametrize("seed", ["00" * 96, b"x" * 95])
def test_replay_records__when_stored_seed_is_not_full_binary__should_report_record(seed):
    content = _pack([{0: REPLAY_VERSION}, {54: seed}])
    with pytest.raises(ValueError, match=r"record 2 at byte .*seed must be a binary"):
        decode_replay_records(content)


@pytest.mark.parametrize("tail", [b"\x81", b"\x81\x01", b"\x81\x01\xdb\x00\x00\x00\x05abc"])
def test_replay_records__when_trailing_record_is_incomplete__should_report_last_complete_position(tail, golden):
    prefix = bytes.fromhex(golden["hex"])
    with pytest.raises(ValueError, match=f"incomplete replay record 6 at byte {len(prefix)}"):
        decode_replay_records(prefix + tail)


@pytest.mark.parametrize(
    "raw", [{999: 1}, {WireKey.EVENT_TYPE: 2}, {True: 1}, [[1]], {1: 999}, {1: 2}, {52: 3}, {6: 1.5}, {54: bytes(97)}]
)
def test_replay_records__when_metadata_or_record_is_invalid__should_report_position(raw):
    content = _pack([{0: REPLAY_VERSION}, raw])
    with pytest.raises(ValueError, match="record 2 at byte"):
        decode_replay_records(content)


@pytest.mark.parametrize("tail", [b"\xc1", b"\x82\x01\x02\x01\x03", b"\x81\x91\x01\x02"])
def test_replay_records__when_map_or_messagepack_is_malformed__should_report_position(tail):
    with pytest.raises(ValueError, match="record 2 at byte"):
        decode_replay_records(_pack([{0: REPLAY_VERSION}]) + tail)


@pytest.mark.parametrize("content", [b"", _pack([{0: "old"}]), b"0" * (MAX_REPLAY_BYTES + 1)])
def test_replay_records__when_header_or_size_is_invalid__should_refuse(content):
    with pytest.raises(ValueError, match=r"version|exceeds"):
        decode_replay_records(content)


@pytest.mark.parametrize(
    "record",
    [
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, "unknown": 1},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.SCORES: {"x": 1}},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.SCORES: {"0": True}},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.SCORES: {0: 1, "0": 2}},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.SCORES: []},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.DORA_INDICATORS: [False]},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.DEALER_DICE: [["x"]]},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.HAND_RESULT: {WireKey.HAN: 1}},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.PLAYERS: [{WireKey.NAME: 1}]},
        {WireKey.EVENT_TYPE: 2, WireKey.PACKED_MOVE: 0, WireKey.HAS_AKADORA: 1},
        {
            WireKey.EVENT_TYPE: 4,
            WireKey.RESULT_TYPE: 999,
            WireKey.RIICHI_STICKS: 0,
            WireKey.DEALER: 0,
            WireKey.DORA_INDICATORS: [],
        },
        {WireKey.EVENT_TYPE: 101, WireKey.SEAT: 0, WireKey.AI_PLAYER: 1},
    ],
)
def test_replay_records__when_event_shape_is_invalid__should_refuse(record):
    with pytest.raises(ValueError, match=r"unknown|invalid|score|misses|unsupported"):
        encode_replay_records([{WireKey.REPLAY_VERSION: REPLAY_VERSION}, record])


def test_replay_records__when_no_records__should_refuse():
    with pytest.raises(ValueError, match="missing its version"):
        encode_replay_records([])


def test_replay_settings__when_standard_and_custom__should_resolve_effective_values():
    standard = encode_replay_settings(GameSettings())
    assert standard == {"id": 1, "overrides": {}}
    assert decode_replay_settings(standard) == STANDARD_RULE_PROFILE.settings
    custom = GameSettings(has_akadora=False, riichi_cost=0, uma=(30, 10, -10, -30))
    reference = encode_replay_settings(custom)
    assert reference == {
        "id": 1,
        "overrides": {"has_akadora": False, "riichi_cost": 0, "uma": [30, 10, -10, -30]},
    }
    assert decode_replay_settings(reference) == custom


@pytest.mark.parametrize(
    "reference",
    [
        {"id": 999, "overrides": {}},
        {"id": True, "overrides": {}},
        {"id": 1, "overrides": {"unknown": True}},
        {"id": 1, "overrides": {"has_akadora": 0}},
        {"id": 1, "overrides": {"starting_score": "25000"}},
        {"id": 1},
    ],
)
def test_replay_settings__when_reference_is_invalid__should_refuse(reference):
    with pytest.raises(ValueError, match=r"unknown rules profile|validation error"):
        decode_replay_settings(reference)


def test_replay_settings__when_unsupported_rule__should_refuse():
    with pytest.raises(UnsupportedSettingsError, match="renhou_value=BAIMAN"):
        decode_replay_settings({"id": 1, "overrides": {"renhou_value": "baiman"}})


def test_replay_settings__when_unknown_selected_profile__should_refuse():
    with pytest.raises(ValueError, match="unknown rules profile"):
        encode_replay_settings(GameSettings(), profile_id=999)


def test_rule_profile__when_defaults_would_fill_fields__should_require_explicit_baseline():
    with pytest.raises(ValueError, match="explicitly define settings"):
        RuleProfile(id=2, settings=GameSettings())


def test_rule_profile__should_pin_persisted_baseline_independently_of_defaults():
    normalized = json.dumps(
        STANDARD_RULE_PROFILE.settings.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    assert (
        hashlib.sha256(normalized.encode()).hexdigest()
        == "c35fef2b4be543aa2eb74373a1993b35639eeb764ae0bb0c77a60f6be6a5c1eb"
    )


@pytest.mark.parametrize(
    ("record_index", "field", "value"),
    [
        (2, WireKey.DORA_INDICATORS, [{}]),
        (1, WireKey.PLAYERS, [0]),
        (1, WireKey.PLAYERS, [{50: 0, 2: 0}]),
        (2, WireKey.PLAYERS, [{50: 0, 51: 250}]),
        (3, WireKey.CLOSED_TILES, [[1]]),
        (3, WireKey.WINNERS, [0]),
        (1, WireKey.DEALER_DICE, [[1, 2]]),
        (1, WireKey.DEALER_DICE, [1, 2]),
        (1, WireKey.DEALER_DICE, [[1], [2, 3]]),
        (3, WireKey.HAND_RESULT, {19: 1, 14: 30, 70: [103], 37: 10, 25: "none"}),
        (3, WireKey.PAO_LIABILITY, {70: [{69: 103, 19: 13, 71: 1}], 55: "all", 20: False}),
    ],
)
def test_replay_records__when_array_has_wrong_element_shape__should_report_damaged_record(
    record_index, field, value, golden
):
    unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
    unpacker.feed(bytes.fromhex(golden["hex"]))
    records = list(unpacker)
    offset = len(_pack(records[:record_index]))
    records[record_index][field] = value
    with pytest.raises(ValueError, match=f"record {record_index + 1} at byte {offset}"):
        decode_replay_records(_pack(records))


def test_replay_records__when_yaku_and_pao_lists__should_preserve_their_distinct_shapes():
    fixture = Path(__file__).parents[4] / "frontend/game_v2/src/fixtures/replays/pao.msgpack"
    content = fixture.read_bytes()
    records = decode_replay_records(content)
    result = next(record for record in records if record.get(WireKey.EVENT_TYPE) == 4)
    assert result[WireKey.HAND_RESULT] == {
        WireKey.HAN: 13,
        WireKey.FU: 40,
        WireKey.YAKU: [{WireKey.YAKU_ID: 103, WireKey.HAN: 13, WireKey.YAKU_YAKUMAN_COUNT: 1}],
        WireKey.POINTS: 320,
        WireKey.HAND_LIMIT: "yakuman",
        WireKey.YAKUMAN_COUNT: 1,
    }
    assert result[WireKey.PAO_LIABILITY] == {WireKey.YAKU: [103], WireKey.PAO_SHARE: "all", WireKey.HONBA_BONUS: False}
    assert encode_replay_records(records) == content
