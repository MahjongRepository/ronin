import gzip
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.logic.rng import RNG_VERSION
from game.replay import loader as replay_loader_module
from game.replay.loader import (
    _MAX_REPLAY_EVENTS,
    ReplayLoadError,
    load_replay_from_file,
    load_replay_from_string,
)
from game.wire.compact import encode_discard
from game.wire.enums import WireRoundResultType
from game.wire.events import EVENT_TYPE_INT
from game.wire.replay_format import REPLAY_VERSION
from shared.lib.melds import MeldData, encode_meld_compact

# Hex seed that produces identity seat assignment: Alice->0, Bob->1, Charlie->2, Diana->3
_TEST_SEED = "0" * 191 + "6"

VERSION_TAG_LINE = json.dumps({"version": REPLAY_VERSION})

GAME_STARTED_LINE = json.dumps(
    {
        "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
        "gid": "test-game",
        "p": [
            {"s": 0, "nm": "Alice", "ai": 0},
            {"s": 1, "nm": "Bob", "ai": 0},
            {"s": 2, "nm": "Charlie", "ai": 0},
            {"s": 3, "nm": "Diana", "ai": 0},
        ],
        "sd": _TEST_SEED,
        "rv": RNG_VERSION,
    },
)

ROUND_STARTED_LINE = json.dumps({"t": EVENT_TYPE_INT[EventType.ROUND_STARTED], "view": {"my_tiles": []}})
DRAW_LINE = json.dumps({"t": EVENT_TYPE_INT[EventType.DRAW], "seat": 0, "tile_id": 108})


def _compact_meld(
    meld_type: str,
    caller_seat: int,
    from_seat: int | None,
    tile_ids: list[int],
    called_tile_id: int | None,
) -> str:
    meld_data = MeldData(
        type="meld",
        meld_type=meld_type,
        caller_seat=caller_seat,
        from_seat=from_seat,
        tile_ids=tile_ids,
        called_tile_id=called_tile_id,
    )
    return json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": encode_meld_compact(meld_data)})


def _build_event_log(*extra_lines: str) -> str:
    return "\n".join([VERSION_TAG_LINE, GAME_STARTED_LINE, *extra_lines])


def test_load_replay__when_discard_event__should_produce_discard_action_for_seat_player():
    discard = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.DISCARD],
            "d": encode_discard(0, 118, is_tsumogiri=False, is_riichi=False),
        },
    )
    content = _build_event_log(ROUND_STARTED_LINE, DRAW_LINE, discard)

    replay = load_replay_from_string(content)
    assert replay.seed == _TEST_SEED
    # player_names is in reconstructed input order (for fill_seats), not seat order
    assert set(replay.player_names) == {"Alice", "Bob", "Charlie", "Diana"}
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.DISCARD
    assert replay.events[0].data == {"tile_id": 118}


def test_load_replay__when_discard_has_riichi_flag__should_produce_declare_riichi_action():
    discard = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.DISCARD],
            "d": encode_discard(1, 50, is_tsumogiri=False, is_riichi=True),
        },
    )
    content = _build_event_log(discard)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.DECLARE_RIICHI
    assert replay.events[0].data == {"tile_id": 50}


def test_load_replay__when_pon_meld__should_produce_call_pon_action():
    # tile_34=2 (3m): tile IDs 8, 9, 10. Called tile 8 from seat 0.
    meld = _compact_meld(meld_type="pon", caller_seat=2, from_seat=0, tile_ids=[8, 9, 10], called_tile_id=8)
    content = _build_event_log(meld)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Charlie"
    assert replay.events[0].action == GameAction.CALL_PON
    assert replay.events[0].data == {"tile_id": 8}


def test_load_replay__when_chi_meld__should_produce_call_chi_action_with_sequence_tiles():
    meld = _compact_meld(meld_type="chi", caller_seat=1, from_seat=0, tile_ids=[20, 24, 28], called_tile_id=20)
    content = _build_event_log(meld)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_CHI
    assert replay.events[0].data == {"tile_id": 20, "sequence_tiles": [24, 28]}


def test_load_replay__when_open_kan_meld__should_produce_open_call_kan_action():
    meld = _compact_meld(meld_type="open_kan", caller_seat=3, from_seat=0, tile_ids=[0, 1, 2, 3], called_tile_id=2)
    content = _build_event_log(meld)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Diana"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 2, "kan_type": "open"}


def test_load_replay__when_closed_kan_meld__should_produce_closed_call_kan_action():
    meld = _compact_meld(
        meld_type="closed_kan", caller_seat=1, from_seat=None, tile_ids=[0, 1, 2, 3], called_tile_id=None
    )
    content = _build_event_log(meld)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 0, "kan_type": "closed"}


def test_load_replay__when_added_kan_meld__should_produce_added_call_kan_action():
    meld = _compact_meld(meld_type="added_kan", caller_seat=0, from_seat=2, tile_ids=[4, 5, 6, 7], called_tile_id=7)
    content = _build_event_log(meld)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 7, "kan_type": "added"}


def test_load_replay__when_round_ends_in_tsumo__should_produce_declare_tsumo_action():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.TSUMO,
            "ws": 2,
            "sch": {},
        },
    )
    content = _build_event_log(round_end)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Charlie"
    assert replay.events[0].action == GameAction.DECLARE_TSUMO


def test_load_replay__when_round_ends_in_ron__should_produce_call_ron_action():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.RON,
            "ws": 1,
            "ls": 0,
        },
    )
    content = _build_event_log(round_end)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_RON


def test_load_replay__when_round_ends_in_double_ron__should_produce_call_ron_for_each_winner():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.DOUBLE_RON,
            "ls": 0,
            "wn": [
                {"ws": 3},
                {"ws": 1},
            ],
        },
    )
    content = _build_event_log(round_end)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 2
    assert replay.events[0].player_name == "Diana"
    assert replay.events[0].action == GameAction.CALL_RON
    assert replay.events[1].player_name == "Bob"
    assert replay.events[1].action == GameAction.CALL_RON


def test_load_replay__when_round_ends_in_nine_terminals__should_produce_call_kyuushu_action():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.ABORTIVE_DRAW,
            "rn": "nine_terminals",
            "s": 0,
        },
    )
    content = _build_event_log(round_end)

    replay = load_replay_from_string(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.CALL_KYUUSHU


def test_load_replay__when_round_ends_without_player_action__should_produce_no_actions():
    cases = [
        (WireRoundResultType.ABORTIVE_DRAW, {"rn": "four_riichi"}),
        (WireRoundResultType.EXHAUSTIVE_DRAW, {"ts": [], "ns": []}),
        (WireRoundResultType.NAGASHI_MANGAN, {}),
    ]
    for rt, extra_fields in cases:
        round_end = json.dumps({"t": EVENT_TYPE_INT[EventType.ROUND_END], "rt": rt, **extra_fields})
        content = _build_event_log(round_end)

        replay = load_replay_from_string(content)
        assert len(replay.events) == 0, f"Expected no events for round_end type {rt}"


def test_load_replay__when_events_are_not_player_actions__should_skip_them():
    content = _build_event_log(
        ROUND_STARTED_LINE,
        DRAW_LINE,
        json.dumps({"t": EVENT_TYPE_INT[EventType.DORA_REVEALED], "tile_id": 54}),
        json.dumps({"t": EVENT_TYPE_INT[EventType.RIICHI_DECLARED], "seat": 0}),
        json.dumps({"t": EVENT_TYPE_INT[EventType.GAME_END], "result": {}}),
    )
    replay = load_replay_from_string(content)
    assert len(replay.events) == 0


def test_load_replay__when_version_tag_missing__should_raise():
    content = GAME_STARTED_LINE
    with pytest.raises(ReplayLoadError, match="must contain at least a version tag"):
        load_replay_from_string(content)


def test_load_replay__when_version_mismatches__should_raise():
    bad_version = json.dumps({"version": "99.0"})
    content = f"{bad_version}\n{GAME_STARTED_LINE}"
    with pytest.raises(ReplayLoadError, match="Replay version mismatch"):
        load_replay_from_string(content)


def test_load_replay__when_first_line_has_no_version_field__should_raise():
    no_version = json.dumps({"something": "else"})
    content = f"{no_version}\n{GAME_STARTED_LINE}"
    with pytest.raises(ReplayLoadError, match="must be a version tag"):
        load_replay_from_string(content)


def test_load_replay__when_first_event_is_not_game_started__should_raise():
    round_started = json.dumps({"t": EVENT_TYPE_INT[EventType.ROUND_STARTED], "view": {}})
    content = f"{VERSION_TAG_LINE}\n{round_started}"
    with pytest.raises(ReplayLoadError, match="First event must be game_started"):
        load_replay_from_string(content)


def test_load_replay__when_json_is_malformed__should_raise():
    content = VERSION_TAG_LINE + "\n{invalid json}"
    with pytest.raises(ReplayLoadError, match="Malformed JSON"):
        load_replay_from_string(content)


def test_load_replay__when_rng_version_missing__should_raise():
    no_version = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "p": [
                {"s": 0, "nm": "A", "ai": 0},
                {"s": 1, "nm": "B", "ai": 0},
                {"s": 2, "nm": "C", "ai": 0},
                {"s": 3, "nm": "D", "ai": 0},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="missing 'rv' field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{no_version}")


def test_load_replay__when_rng_version_mismatches__should_raise():
    bad_version = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": "old-version-v0",
            "p": [
                {"s": 0, "nm": "A", "ai": 0},
                {"s": 1, "nm": "B", "ai": 0},
                {"s": 2, "nm": "C", "ai": 0},
                {"s": 3, "nm": "D", "ai": 0},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="RNG version mismatch"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_version}")


def test_load_replay__when_seed_missing__should_raise():
    no_seed = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "p": [
                {"s": 0, "nm": "A"},
                {"s": 1, "nm": "B"},
                {"s": 2, "nm": "C"},
                {"s": 3, "nm": "D"},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="missing 'sd' field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{no_seed}")


@pytest.mark.parametrize("seed", ["not-hex-seed" + "0" * 180, 12345])
def test_load_replay__when_seed_is_not_a_hex_string__should_raise(seed: str | int):
    bad_seed = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": seed,
            "rv": RNG_VERSION,
            "p": [
                {"s": 0, "nm": "A", "ai": 0},
                {"s": 1, "nm": "B", "ai": 0},
                {"s": 2, "nm": "C", "ai": 0},
                {"s": 3, "nm": "D", "ai": 0},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="invalid seed"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_seed}")


def test_load_replay__when_event_type_unknown__should_raise():
    content = _build_event_log(json.dumps({"t": 999}))
    with pytest.raises(ReplayLoadError, match="Unknown event type"):
        load_replay_from_string(content)


def test_load_replay__when_event_type_missing__should_raise():
    content = _build_event_log(json.dumps({"seat": 0, "tile_id": 10}))
    with pytest.raises(ReplayLoadError, match="Event missing required 't' field"):
        load_replay_from_string(content)


def test_load_replay__when_content_is_empty__should_raise():
    with pytest.raises(ReplayLoadError, match="Empty replay content"):
        load_replay_from_string("")


def test_load_replay_from_file__when_plain_text_file__should_load_replay(tmp_path: Path):
    discard = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.DISCARD],
            "d": encode_discard(0, 118, is_tsumogiri=False, is_riichi=False),
        },
    )
    content = _build_event_log(discard)
    file_path = tmp_path / "test.txt"
    file_path.write_text(content)

    replay = load_replay_from_file(file_path)
    assert replay.seed == _TEST_SEED
    assert len(replay.events) == 1


def test_load_replay_from_file__when_gzip_file__should_load_replay(tmp_path: Path):
    discard = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.DISCARD],
            "d": encode_discard(0, 118, is_tsumogiri=False, is_riichi=False),
        },
    )
    content = _build_event_log(discard)
    file_path = tmp_path / "test.txt.gz"
    file_path.write_bytes(gzip.compress(content.encode("utf-8")))

    replay = load_replay_from_file(file_path)
    assert replay.seed == _TEST_SEED
    assert len(replay.events) == 1


def test_load_replay_from_file__when_file_unreadable__should_raise():
    with pytest.raises(ReplayLoadError, match="Cannot read replay file"):
        load_replay_from_file("/nonexistent/path/replay.txt")


def test_load_replay_from_file__when_gzip_is_corrupted__should_raise(tmp_path: Path):
    file_path = tmp_path / "corrupted.txt.gz"
    file_path.write_bytes(b"not valid gzip data at all")

    with pytest.raises(ReplayLoadError, match="Cannot read replay file"):
        load_replay_from_file(file_path)


def test_load_replay__when_players_missing__should_raise():
    no_players = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": RNG_VERSION,
        },
    )
    with pytest.raises(ReplayLoadError, match="missing 'p' field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{no_players}")


def test_load_replay__when_round_end_result_type_unknown__should_raise():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": 99,
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="Unknown round_end result type"):
        load_replay_from_string(content)


def test_load_replay__when_discard_missing_packed_value__should_raise():
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD]})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="discard event missing 'd' field"):
        load_replay_from_string(content)


def test_load_replay__when_discard_packed_value_invalid__should_raise():
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD], "d": 9999})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="Invalid discard packed value"):
        load_replay_from_string(content)


def test_load_replay__when_meld_missing_compact_value__should_raise():
    meld = json.dumps({"t": EVENT_TYPE_INT[EventType.MELD]})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="Compact meld event missing 'm' field"):
        load_replay_from_string(content)


def test_load_replay__when_meld_compact_value_corrupt__should_raise():
    meld = json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": 999999})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="Invalid compact meld value"):
        load_replay_from_string(content)


def test_load_replay__when_discard_references_unknown_seat__should_raise(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        replay_loader_module,
        "decode_discard",
        lambda _d: (9, 0, False, False),
    )

    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD], "d": 0})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="discard event references unknown seat"):
        load_replay_from_string(content)


def test_load_replay__when_meld_references_unknown_seat__should_raise(monkeypatch: pytest.MonkeyPatch):
    fake_meld_data = MeldData(
        type="meld",
        meld_type="pon",
        caller_seat=9,
        from_seat=0,
        tile_ids=[0, 1, 2],
        called_tile_id=0,
    )
    monkeypatch.setattr(replay_loader_module, "decode_meld_compact", lambda _v: fake_meld_data)

    meld = json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": 0})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="meld event references unknown seat"):
        load_replay_from_string(content)


def test_load_replay__when_meld_type_unknown__should_raise(monkeypatch: pytest.MonkeyPatch):
    fake_meld_data = MeldData(
        type="meld",
        meld_type="bogus",
        caller_seat=0,
        from_seat=1,
        tile_ids=[0, 1, 2],
        called_tile_id=0,
    )
    monkeypatch.setattr(replay_loader_module, "decode_meld_compact", lambda _v: fake_meld_data)

    meld = json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": 0})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="Unknown meld_type in decoded IMME"):
        load_replay_from_string(content)


def test_load_replay__when_player_seats_are_not_0_to_3__should_raise():
    bad_started = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": RNG_VERSION,
            "p": [
                {"s": 0, "nm": "A"},
                {"s": 1, "nm": "B"},
                {"s": 2, "nm": "C"},
                {"s": 5, "nm": "D"},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="must have exactly seats"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_started}")


def test_load_replay__when_tsumo_round_end_missing_winner_seat__should_raise():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.TSUMO,
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="tsumo round_end missing or invalid field"):
        load_replay_from_string(content)


def test_load_replay__when_ron_round_end_missing_winner_seat__should_raise():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.RON,
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="ron round_end missing or invalid field"):
        load_replay_from_string(content)


def test_load_replay__when_double_ron_has_no_winners__should_raise():
    # Empty winners list
    round_end_empty = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.DOUBLE_RON,
            "wn": [],
        },
    )
    with pytest.raises(ReplayLoadError, match="must have at least one winner"):
        load_replay_from_string(_build_event_log(round_end_empty))

    # Missing winners field
    round_end_missing = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.DOUBLE_RON,
        },
    )
    with pytest.raises(ReplayLoadError, match="must have at least one winner"):
        load_replay_from_string(_build_event_log(round_end_missing))


def test_load_replay__when_double_ron_winner_missing_seat__should_raise():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.DOUBLE_RON,
            "wn": [{"some_field": 1}],
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="double_ron round_end missing or invalid field"):
        load_replay_from_string(content)


def test_load_replay__when_nine_terminals_missing_seat__should_raise():
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.ABORTIVE_DRAW,
            "rn": "nine_terminals",
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="nine_terminals abortive_draw missing or invalid field"):
        load_replay_from_string(content)


def test_load_replay__when_discard_packed_value_is_bool__should_raise():
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD], "d": True})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="Invalid discard packed value"):
        load_replay_from_string(content)


def test_load_replay__when_event_count_exceeds_maximum__should_raise():
    events = [VERSION_TAG_LINE, GAME_STARTED_LINE]
    filler = json.dumps({"t": EVENT_TYPE_INT[EventType.DRAW], "seat": 0, "tile_id": 0})
    events.extend([filler] * _MAX_REPLAY_EVENTS)
    content = "\n".join(events)

    with pytest.raises(ReplayLoadError, match="maximum event count"):
        load_replay_from_string(content)


def test_load_replay__when_player_entry_is_not_a_dict__should_raise():
    bad_started = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": RNG_VERSION,
            "p": ["Alice", "Bob", "Charlie", "Diana"],
        },
    )
    with pytest.raises(ReplayLoadError, match="player entry 0 is not a dict"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_started}")


def test_load_replay__when_player_entry_missing_seat__should_raise():
    bad_started = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": RNG_VERSION,
            "p": [
                {"nm": "A"},
                {"s": 1, "nm": "B"},
                {"s": 2, "nm": "C"},
                {"s": 3, "nm": "D"},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="player entry 0 missing required field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_started}")


def test_load_replay__when_player_entry_seat_is_not_integer__should_raise():
    bad_started = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": RNG_VERSION,
            "p": [
                {"s": "zero", "nm": "A"},
                {"s": 1, "nm": "B"},
                {"s": 2, "nm": "C"},
                {"s": 3, "nm": "D"},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="non-integer seat"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_started}")


def test_load_replay__when_event_type_is_bool__should_raise():
    content = _build_event_log(json.dumps({"t": True, "seat": 0, "tile_id": 5}))
    with pytest.raises(ReplayLoadError, match="'t' field must be an integer"):
        load_replay_from_string(content)


def test_load_replay__when_meld_value_is_bool__should_raise():
    content = _build_event_log(json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": True}))
    with pytest.raises(ReplayLoadError, match="'m' field must be an integer"):
        load_replay_from_string(content)


def test_load_replay__when_player_entry_name_is_empty__should_raise():
    bad_started = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": _TEST_SEED,
            "rv": RNG_VERSION,
            "p": [
                {"s": 0, "nm": ""},
                {"s": 1, "nm": "B"},
                {"s": 2, "nm": "C"},
                {"s": 3, "nm": "D"},
            ],
        },
    )
    with pytest.raises(ReplayLoadError, match="invalid name"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_started}")
