"""Tests for replay loader: event-log parsing, action extraction, error handling."""

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from game.logic.enums import GameAction, WireRoundResultType
from game.logic.events import EventType
from game.logic.rng import RNG_VERSION
from game.messaging.compact import encode_discard
from game.messaging.event_payload import EVENT_TYPE_INT
from game.replay import loader as replay_loader_module
from game.replay.loader import (
    _MAX_REPLAY_EVENTS,
    ReplayLoadError,
    load_replay_from_file,
    load_replay_from_string,
)
from game.replay.models import REPLAY_VERSION
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
    """Encode a meld as compact JSON: {"t": 0, "m": <IMME_int>}."""
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
    """Build a newline-delimited event-log string."""
    return "\n".join([VERSION_TAG_LINE, GAME_STARTED_LINE, *extra_lines])


def test_parse_single_discard():
    """Parse a discard event into a DISCARD action."""
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


def test_discard_with_riichi_maps_to_declare_riichi():
    """Discard with is_riichi=true maps to DECLARE_RIICHI action."""
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


def test_meld_pon():
    """Compact meld event with pon maps to CALL_PON."""
    # tile_34=2 (3m): tile IDs 8, 9, 10. Called tile 8 from seat 0.
    meld = _compact_meld("pon", caller_seat=2, from_seat=0, tile_ids=[8, 9, 10], called_tile_id=8)
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Charlie"
    assert replay.events[0].action == GameAction.CALL_PON
    assert replay.events[0].data == {"tile_id": 8}


def test_meld_chi():
    """Compact meld event with chi maps to CALL_CHI with sequence_tiles."""
    meld = _compact_meld("chi", caller_seat=1, from_seat=0, tile_ids=[20, 24, 28], called_tile_id=20)
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_CHI
    assert replay.events[0].data == {"tile_id": 20, "sequence_tiles": [24, 28]}


def test_meld_open_kan():
    """Compact meld event with open_kan maps to CALL_KAN using called_tile_id."""
    meld = _compact_meld("open_kan", caller_seat=3, from_seat=0, tile_ids=[0, 1, 2, 3], called_tile_id=2)
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Diana"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 2, "kan_type": "open"}


def test_meld_closed_kan():
    """Compact meld event with closed_kan maps to CALL_KAN with kan_type=closed."""
    meld = _compact_meld("closed_kan", caller_seat=1, from_seat=None, tile_ids=[0, 1, 2, 3], called_tile_id=None)
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 0, "kan_type": "closed"}


def test_meld_added_kan():
    """Compact meld event with added_kan maps to CALL_KAN with kan_type=added."""
    meld = _compact_meld("added_kan", caller_seat=0, from_seat=2, tile_ids=[4, 5, 6, 7], called_tile_id=7)
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 7, "kan_type": "added"}


def test_round_end_tsumo():
    """round_end with tsumo result maps to DECLARE_TSUMO."""
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


def test_round_end_ron():
    """round_end with ron result maps to CALL_RON."""
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


def test_round_end_double_ron():
    """round_end with double_ron produces two CALL_RON in winners list order."""
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


def test_round_end_abortive_nine_terminals():
    """round_end with abortive nine_terminals maps to CALL_KYUUSHU."""
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


def test_non_scoring_round_ends_produce_no_actions():
    """round_end types that don't imply a player action produce no actions."""
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


def test_non_action_events_skipped():
    """Known non-action events (draw, dora_revealed, etc.) are silently skipped."""
    content = _build_event_log(
        ROUND_STARTED_LINE,
        DRAW_LINE,
        json.dumps({"t": EVENT_TYPE_INT[EventType.DORA_REVEALED], "tile_id": 54}),
        json.dumps({"t": EVENT_TYPE_INT[EventType.RIICHI_DECLARED], "seat": 0}),
        json.dumps({"t": EVENT_TYPE_INT[EventType.GAME_END], "result": {}}),
    )
    replay = load_replay_from_string(content)

    assert len(replay.events) == 0


def test_error_missing_version_tag():
    """ReplayLoadError when replay has only one event (no version tag + game_started pair)."""
    content = GAME_STARTED_LINE
    with pytest.raises(ReplayLoadError, match="must contain at least a version tag"):
        load_replay_from_string(content)


def test_error_version_mismatch():
    """ReplayLoadError when version tag has wrong version."""
    bad_version = json.dumps({"version": "99.0"})
    content = f"{bad_version}\n{GAME_STARTED_LINE}"
    with pytest.raises(ReplayLoadError, match="Replay version mismatch"):
        load_replay_from_string(content)


def test_error_missing_version_field():
    """ReplayLoadError when first event has no 'version' field."""
    no_version = json.dumps({"something": "else"})
    content = f"{no_version}\n{GAME_STARTED_LINE}"
    with pytest.raises(ReplayLoadError, match="must be a version tag"):
        load_replay_from_string(content)


def test_error_missing_game_started():
    """ReplayLoadError when second event is not game_started."""
    round_started = json.dumps({"t": EVENT_TYPE_INT[EventType.ROUND_STARTED], "view": {}})
    content = f"{VERSION_TAG_LINE}\n{round_started}"
    with pytest.raises(ReplayLoadError, match="First event must be game_started"):
        load_replay_from_string(content)


def test_error_malformed_json():
    """ReplayLoadError for malformed JSON."""
    content = VERSION_TAG_LINE + "\n{invalid json}"
    with pytest.raises(ReplayLoadError, match="Malformed JSON"):
        load_replay_from_string(content)


def test_error_missing_rng_version():
    """ReplayLoadError when game_started missing rv."""
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


def test_error_rng_version_mismatch():
    """ReplayLoadError when game_started has wrong rng_version."""
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


def test_error_missing_seed():
    """ReplayLoadError when game_started missing sd."""
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


def test_error_non_hex_seed():
    """ReplayLoadError when seed contains non-hex characters."""
    bad_seed = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.GAME_STARTED],
            "gid": "test",
            "sd": "not-hex-seed" + "0" * 180,
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


def test_error_unknown_event_type():
    """ReplayLoadError for unknown integer event type."""
    content = _build_event_log(json.dumps({"t": 999}))
    with pytest.raises(ReplayLoadError, match="Unknown event type"):
        load_replay_from_string(content)


def test_error_missing_event_type():
    """ReplayLoadError when event has no 't' field."""
    content = _build_event_log(json.dumps({"seat": 0, "tile_id": 10}))
    with pytest.raises(ReplayLoadError, match="Event missing required 't' field"):
        load_replay_from_string(content)


def test_error_empty_content():
    """ReplayLoadError for empty content."""
    with pytest.raises(ReplayLoadError, match="Empty replay content"):
        load_replay_from_string("")


def test_load_replay_from_file(tmp_path: Path):
    """load_replay_from_file reads from a file path."""
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


def test_load_replay_from_file_io_error():
    """ReplayLoadError for missing file."""
    with pytest.raises(ReplayLoadError, match="Cannot read replay file"):
        load_replay_from_file("/nonexistent/path/replay.txt")


def test_error_missing_players():
    """ReplayLoadError when game_started missing p."""
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


def test_error_unknown_round_end_result_type():
    """ReplayLoadError for unknown round_end result type."""
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": 99,
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="Unknown round_end result type"):
        load_replay_from_string(content)


def test_error_discard_missing_d_field():
    """ReplayLoadError when discard event missing 'd' field."""
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD]})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="discard event missing 'd' field"):
        load_replay_from_string(content)


def test_error_discard_invalid_packed_value():
    """ReplayLoadError when discard event has out-of-range packed value."""
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD], "d": 9999})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="Invalid discard packed value"):
        load_replay_from_string(content)


def test_error_discard_unknown_seat(monkeypatch: pytest.MonkeyPatch):
    """ReplayLoadError when decoded discard references a seat not in game_started."""
    monkeypatch.setattr(
        replay_loader_module,
        "decode_discard",
        lambda _d: (9, 0, False, False),
    )
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD], "d": 0})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="discard event references unknown seat"):
        load_replay_from_string(content)


def test_error_compact_meld_missing_m_field():
    """ReplayLoadError when compact meld event has no 'm' field."""
    meld = json.dumps({"t": EVENT_TYPE_INT[EventType.MELD]})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="Compact meld event missing 'm' field"):
        load_replay_from_string(content)


def test_error_compact_meld_unknown_seat(monkeypatch: pytest.MonkeyPatch):
    """ReplayLoadError when decoded meld references a seat not in game_started."""
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


def test_error_compact_meld_unknown_meld_type(monkeypatch: pytest.MonkeyPatch):
    """ReplayLoadError when decoded meld has an unknown meld_type."""
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


def test_error_compact_meld_corrupt_value():
    """ReplayLoadError when compact meld value is out of range."""
    meld = json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": 999999})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="Invalid compact meld value"):
        load_replay_from_string(content)


def test_error_invalid_seat_indices():
    """ReplayLoadError when player seats are not {0, 1, 2, 3}."""
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


def test_error_round_end_tsumo_missing_winner_seat():
    """ReplayLoadError when tsumo round_end missing ws."""
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.TSUMO,
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="tsumo round_end missing or invalid field"):
        load_replay_from_string(content)


def test_error_ron_round_end_missing_winner_seat():
    """ReplayLoadError when ron round_end missing ws."""
    round_end = json.dumps(
        {
            "t": EVENT_TYPE_INT[EventType.ROUND_END],
            "rt": WireRoundResultType.RON,
        },
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="ron round_end missing or invalid field"):
        load_replay_from_string(content)


def test_error_double_ron_no_valid_winners():
    """ReplayLoadError when double_ron has no valid winners (empty or missing)."""
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


def test_error_double_ron_winner_missing_seat():
    """ReplayLoadError when double_ron winner entry missing ws."""
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


def test_error_abortive_draw_nine_terminals_missing_seat():
    """ReplayLoadError when nine_terminals abortive_draw missing s."""
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


def test_error_discard_boolean_packed_value():
    """ReplayLoadError when discard event has a boolean packed value."""
    discard = json.dumps({"t": EVENT_TYPE_INT[EventType.DISCARD], "d": True})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="Invalid discard packed value"):
        load_replay_from_string(content)


def test_error_exceeds_max_replay_events():
    """ReplayLoadError when replay content exceeds the maximum event count."""
    events = [VERSION_TAG_LINE, GAME_STARTED_LINE]
    filler = json.dumps({"t": EVENT_TYPE_INT[EventType.DRAW], "seat": 0, "tile_id": 0})
    events.extend([filler] * _MAX_REPLAY_EVENTS)
    content = "\n".join(events)
    with pytest.raises(ReplayLoadError, match="maximum event count"):
        load_replay_from_string(content)


def test_error_player_entry_not_dict():
    """ReplayLoadError when a game_started player entry is not a dict."""
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


def test_error_player_entry_missing_seat():
    """ReplayLoadError when a game_started player entry is missing 's'."""
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


def test_error_player_entry_non_integer_seat():
    """ReplayLoadError when a game_started player entry has a non-integer seat."""
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


def test_error_boolean_event_type():
    """ReplayLoadError when event 't' field is a boolean instead of int."""
    content = _build_event_log(json.dumps({"t": True, "seat": 0, "tile_id": 5}))
    with pytest.raises(ReplayLoadError, match="'t' field must be an integer"):
        load_replay_from_string(content)


def test_error_boolean_meld_value():
    """ReplayLoadError when meld 'm' field is a boolean instead of int."""
    content = _build_event_log(json.dumps({"t": EVENT_TYPE_INT[EventType.MELD], "m": True}))
    with pytest.raises(ReplayLoadError, match="'m' field must be an integer"):
        load_replay_from_string(content)


def test_error_player_entry_empty_name():
    """ReplayLoadError when a game_started player entry has an empty name."""
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
