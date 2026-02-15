"""Tests for replay loader: event-log parsing, action extraction, error handling."""

import json
from pathlib import Path

import pytest

from game.logic.enums import GameAction
from game.logic.rng import RNG_VERSION
from game.replay.loader import ReplayLoadError, load_replay_from_file, load_replay_from_string
from game.replay.models import REPLAY_VERSION

# Hex seed that produces identity seat assignment: Alice->0, Bob->1, Charlie->2, Diana->3
_TEST_SEED = "0" * 191 + "6"

VERSION_TAG_LINE = json.dumps({"version": REPLAY_VERSION})

GAME_STARTED_LINE = json.dumps(
    {
        "type": "game_started",
        "game_id": "test-game",
        "players": [
            {"seat": 0, "name": "Alice", "is_ai_player": False},
            {"seat": 1, "name": "Bob", "is_ai_player": False},
            {"seat": 2, "name": "Charlie", "is_ai_player": False},
            {"seat": 3, "name": "Diana", "is_ai_player": False},
        ],
        "seed": _TEST_SEED,
        "rng_version": RNG_VERSION,
    }
)

ROUND_STARTED_LINE = json.dumps({"type": "round_started", "view": {"my_tiles": []}})
DRAW_LINE = json.dumps({"type": "draw", "seat": 0, "tile_id": 108})


def _build_event_log(*extra_lines: str) -> str:
    """Build an event-log string with version tag, game_started header, and extra lines."""
    return "\n".join([VERSION_TAG_LINE, GAME_STARTED_LINE, *extra_lines])


def test_parse_single_discard():
    """Parse a discard event into a DISCARD action."""
    discard = json.dumps(
        {
            "type": "discard",
            "seat": 0,
            "tile_id": 118,
            "is_tsumogiri": False,
            "is_riichi": False,
        }
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
            "type": "discard",
            "seat": 1,
            "tile_id": 50,
            "is_tsumogiri": False,
            "is_riichi": True,
        }
    )
    content = _build_event_log(discard)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.DECLARE_RIICHI
    assert replay.events[0].data == {"tile_id": 50}


def test_meld_pon():
    """Meld event with type pon maps to CALL_PON."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": 2,
            "from_seat": 0,
            "tile_ids": [10, 11, 12],
            "called_tile_id": 10,
        }
    )
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Charlie"
    assert replay.events[0].action == GameAction.CALL_PON
    assert replay.events[0].data == {"tile_id": 10}


def test_meld_chi():
    """Meld event with type chi maps to CALL_CHI with sequence_tiles."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": 1,
            "from_seat": 0,
            "tile_ids": [20, 24, 28],
            "called_tile_id": 20,
        }
    )
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_CHI
    assert replay.events[0].data == {"tile_id": 20, "sequence_tiles": [24, 28]}


def test_meld_open_kan():
    """Meld event with type open_kan maps to CALL_KAN."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "open_kan",
            "caller_seat": 3,
            "tile_ids": [0, 1, 2, 3],
            "called_tile_id": 0,
        }
    )
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Diana"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 0, "kan_type": "open"}


def test_meld_added_kan():
    """Meld event with type added_kan maps to CALL_KAN with kan_type=added."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "added_kan",
            "caller_seat": 0,
            "tile_ids": [4, 5, 6, 7],
            "called_tile_id": 7,
        }
    )
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
            "type": "round_end",
            "result": {"type": "tsumo", "winner_seat": 2, "score_changes": {}},
        }
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
            "type": "round_end",
            "result": {"type": "ron", "winner_seat": 1, "loser_seat": 0},
        }
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
            "type": "round_end",
            "result": {
                "type": "double_ron",
                "loser_seat": 0,
                "winners": [
                    {"winner_seat": 3},
                    {"winner_seat": 1},
                ],
            },
        }
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
            "type": "round_end",
            "result": {"type": "abortive_draw", "reason": "nine_terminals", "seat": 0},
        }
    )
    content = _build_event_log(round_end)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.CALL_KYUUSHU


def test_round_end_abortive_other_skipped():
    """round_end with non-nine_terminals abortive draw produces no actions."""
    round_end = json.dumps(
        {
            "type": "round_end",
            "result": {"type": "abortive_draw", "reason": "four_riichi"},
        }
    )
    content = _build_event_log(round_end)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 0


def test_round_end_exhaustive_draw_skipped():
    """round_end with exhaustive_draw produces no actions."""
    round_end = json.dumps(
        {
            "type": "round_end",
            "result": {"type": "exhaustive_draw", "tempai_seats": [], "noten_seats": []},
        }
    )
    content = _build_event_log(round_end)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 0


def test_non_action_events_skipped():
    """Known non-action events (draw, dora_revealed, etc.) are silently skipped."""
    content = _build_event_log(
        ROUND_STARTED_LINE,
        DRAW_LINE,
        json.dumps({"type": "dora_revealed", "tile_id": 54}),
        json.dumps({"type": "riichi_declared", "seat": 0}),
        json.dumps({"type": "game_end", "result": {}}),
    )
    replay = load_replay_from_string(content)

    assert len(replay.events) == 0


def test_error_missing_version_tag():
    """ReplayLoadError when first line is not a version tag."""
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
    """ReplayLoadError when first line has no 'version' field."""
    no_version = json.dumps({"something": "else"})
    content = f"{no_version}\n{GAME_STARTED_LINE}"
    with pytest.raises(ReplayLoadError, match="must be a version tag"):
        load_replay_from_string(content)


def test_error_missing_game_started():
    """ReplayLoadError when second event is not game_started."""
    content = "\n".join([VERSION_TAG_LINE, json.dumps({"type": "round_started", "view": {}})])
    with pytest.raises(ReplayLoadError, match="First event must be game_started"):
        load_replay_from_string(content)


def test_error_malformed_json():
    """ReplayLoadError for malformed JSON."""
    content = VERSION_TAG_LINE + "\n" + GAME_STARTED_LINE + "\n{invalid json}"
    with pytest.raises(ReplayLoadError, match="Malformed JSON on line 3"):
        load_replay_from_string(content)


def test_error_missing_rng_version():
    """ReplayLoadError when game_started missing rng_version."""
    no_version = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": _TEST_SEED,
            "players": [
                {"seat": 0, "name": "A", "is_ai_player": False},
                {"seat": 1, "name": "B", "is_ai_player": False},
                {"seat": 2, "name": "C", "is_ai_player": False},
                {"seat": 3, "name": "D", "is_ai_player": False},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="missing 'rng_version' field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{no_version}")


def test_error_rng_version_mismatch():
    """ReplayLoadError when game_started has wrong rng_version."""
    bad_version = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": _TEST_SEED,
            "rng_version": "old-version-v0",
            "players": [
                {"seat": 0, "name": "A", "is_ai_player": False},
                {"seat": 1, "name": "B", "is_ai_player": False},
                {"seat": 2, "name": "C", "is_ai_player": False},
                {"seat": 3, "name": "D", "is_ai_player": False},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="RNG version mismatch"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_version}")


def test_error_missing_seed():
    """ReplayLoadError when game_started missing seed."""
    no_seed = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "players": [
                {"seat": 0, "name": "A"},
                {"seat": 1, "name": "B"},
                {"seat": 2, "name": "C"},
                {"seat": 3, "name": "D"},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="missing 'seed' field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{no_seed}")


def test_error_non_hex_seed():
    """ReplayLoadError when seed contains non-hex characters."""
    bad_seed = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": "not-hex-seed" + "0" * 180,
            "rng_version": RNG_VERSION,
            "players": [
                {"seat": 0, "name": "A", "is_ai_player": False},
                {"seat": 1, "name": "B", "is_ai_player": False},
                {"seat": 2, "name": "C", "is_ai_player": False},
                {"seat": 3, "name": "D", "is_ai_player": False},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="invalid seed"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_seed}")


def test_error_short_hex_seed():
    """ReplayLoadError when seed is valid hex but wrong length."""
    bad_seed = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": "abc",
            "rng_version": RNG_VERSION,
            "players": [
                {"seat": 0, "name": "A", "is_ai_player": False},
                {"seat": 1, "name": "B", "is_ai_player": False},
                {"seat": 2, "name": "C", "is_ai_player": False},
                {"seat": 3, "name": "D", "is_ai_player": False},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="invalid seed"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_seed}")


def test_error_non_string_seed():
    """ReplayLoadError when seed is not a string (e.g., integer from malformed JSON)."""
    bad_seed = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": 12345,
            "rng_version": RNG_VERSION,
            "players": [
                {"seat": 0, "name": "A", "is_ai_player": False},
                {"seat": 1, "name": "B", "is_ai_player": False},
                {"seat": 2, "name": "C", "is_ai_player": False},
                {"seat": 3, "name": "D", "is_ai_player": False},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="invalid seed"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_seed}")


def test_error_unknown_event_type():
    """ReplayLoadError for unknown event type."""
    content = _build_event_log(json.dumps({"type": "totally_new_event"}))
    with pytest.raises(ReplayLoadError, match="Unknown event type"):
        load_replay_from_string(content)


def test_error_empty_content():
    """ReplayLoadError for empty content."""
    with pytest.raises(ReplayLoadError, match="Empty replay content"):
        load_replay_from_string("")


def test_load_replay_from_file(tmp_path: Path):
    """load_replay_from_file reads from a file path."""
    discard = json.dumps(
        {
            "type": "discard",
            "seat": 0,
            "tile_id": 118,
            "is_tsumogiri": False,
            "is_riichi": False,
        }
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
    """ReplayLoadError when game_started missing players."""
    no_players = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": _TEST_SEED,
            "rng_version": RNG_VERSION,
        }
    )
    with pytest.raises(ReplayLoadError, match="missing 'players' field"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{no_players}")


def test_error_unknown_meld_type():
    """ReplayLoadError for unknown meld_type."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "unknown_meld",
            "caller_seat": 0,
            "tile_ids": [0],
            "called_tile_id": 0,
        }
    )
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="Unknown meld_type"):
        load_replay_from_string(content)


def test_error_unknown_round_end_result_type():
    """ReplayLoadError for unknown round_end result type."""
    round_end = json.dumps(
        {
            "type": "round_end",
            "result": {"type": "unknown_result"},
        }
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="Unknown round_end result type"):
        load_replay_from_string(content)


def test_error_discard_missing_seat():
    """ReplayLoadError when discard event missing 'seat' field."""
    discard = json.dumps({"type": "discard", "tile_id": 10})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="discard event missing required field"):
        load_replay_from_string(content)


def test_error_discard_missing_tile_id():
    """ReplayLoadError when discard event missing 'tile_id' field."""
    discard = json.dumps({"type": "discard", "seat": 0})
    content = _build_event_log(discard)
    with pytest.raises(ReplayLoadError, match="discard event missing required field"):
        load_replay_from_string(content)


def test_error_meld_missing_caller_seat():
    """ReplayLoadError when meld event missing 'caller_seat' field."""
    meld = json.dumps({"type": "meld", "meld_type": "pon", "called_tile_id": 0})
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="meld event missing required field"):
        load_replay_from_string(content)


def test_meld_kan_falls_back_to_called_tile_id():
    """Kan meld with empty tile_ids falls back to called_tile_id."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "closed_kan",
            "caller_seat": 3,
            "tile_ids": [],
            "called_tile_id": 5,
        }
    )
    content = _build_event_log(meld)
    replay = load_replay_from_string(content)

    assert len(replay.events) == 1
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 5, "kan_type": "closed"}


def test_error_kan_missing_tile_ids_and_called_tile_id():
    """ReplayLoadError when kan meld missing both tile_ids and called_tile_id."""
    meld = json.dumps(
        {
            "type": "meld",
            "meld_type": "closed_kan",
            "caller_seat": 0,
        }
    )
    content = _build_event_log(meld)
    with pytest.raises(ReplayLoadError, match="missing both 'tile_ids' and 'called_tile_id'"):
        load_replay_from_string(content)


def test_error_invalid_seat_indices():
    """ReplayLoadError when player seats are not {0, 1, 2, 3}."""
    bad_started = json.dumps(
        {
            "type": "game_started",
            "game_id": "test",
            "seed": _TEST_SEED,
            "rng_version": RNG_VERSION,
            "players": [
                {"seat": 0, "name": "A"},
                {"seat": 1, "name": "B"},
                {"seat": 2, "name": "C"},
                {"seat": 5, "name": "D"},
            ],
        }
    )
    with pytest.raises(ReplayLoadError, match="must have exactly seats"):
        load_replay_from_string(f"{VERSION_TAG_LINE}\n{bad_started}")


def test_error_round_end_tsumo_missing_winner_seat():
    """ReplayLoadError when tsumo round_end missing winner_seat."""
    round_end = json.dumps(
        {
            "type": "round_end",
            "result": {"type": "tsumo"},
        }
    )
    content = _build_event_log(round_end)
    with pytest.raises(ReplayLoadError, match="tsumo round_end missing or invalid field"):
        load_replay_from_string(content)
