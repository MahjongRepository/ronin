import gzip
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.logic.rng import RNG_VERSION
from game.logic.settings import GameSettings
from game.replay import loader as replay_loader_module
from game.replay.loader import (
    _MAX_REPLAY_EVENTS,
    ReplayLoadError,
    load_replay_from_bytes,
    load_replay_from_file,
    load_replay_records,
)
from game.wire import replay_format
from game.wire.compact import encode_discard
from game.wire.enums import SeatControlReason, WireRoundResultType
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey
from game.wire.replay_format import REPLAY_VERSION, ReplayLineType, encode_replay_records, encode_replay_settings
from shared.lib.melds import MeldData, encode_meld_compact

_TEST_SEED = "0" * 191 + "6"
VERSION_RECORD: dict[int, object] = {WireKey.REPLAY_VERSION: REPLAY_VERSION}
GAME_STARTED: dict[int, object] = {
    WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
    WireKey.GAME_ID: "test-game",
    WireKey.GAME_TYPE: 0,
    WireKey.DEALER: 0,
    WireKey.DEALER_DICE: [[1, 1], [1, 1]],
    WireKey.RIICHI_STICK_VALUE: 10,
    WireKey.HAS_AKADORA: True,
    WireKey.PLAYERS: [
        {WireKey.SEAT: 0, WireKey.NAME: "Alice", WireKey.AI_PLAYER: 0},
        {WireKey.SEAT: 1, WireKey.NAME: "Bob", WireKey.AI_PLAYER: 0},
        {WireKey.SEAT: 2, WireKey.NAME: "Charlie", WireKey.AI_PLAYER: 0},
        {WireKey.SEAT: 3, WireKey.NAME: "Diana", WireKey.AI_PLAYER: 0},
    ],
    WireKey.SEED: _TEST_SEED,
    WireKey.RNG_VERSION: RNG_VERSION,
    WireKey.GAME_SETTINGS: encode_replay_settings(GameSettings()),
}
GAME_STARTED_RECORD = GAME_STARTED
ROUND_STARTED_RECORD = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_STARTED]}
DRAW_RECORD = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DRAW], WireKey.PACKED_MOVE: 108}


def _compact_meld(
    *,
    meld_type: str,
    caller_seat: int,
    from_seat: int | None,
    tile_ids: list[int],
    called_tile_id: int | None,
    added_tile_id: int | None = None,
) -> dict[int, object]:
    meld_data = MeldData(
        type="meld",
        meld_type=meld_type,
        caller_seat=caller_seat,
        from_seat=from_seat,
        tile_ids=tile_ids,
        called_tile_id=called_tile_id,
        added_tile_id=added_tile_id,
    )
    return {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.MELD], WireKey.PACKED_MELD: encode_meld_compact(meld_data)}


def _build_records(*extra_records: dict[int, object]) -> list[dict[int, object]]:
    return [VERSION_RECORD, GAME_STARTED_RECORD, *extra_records]


def test_load_replay__when_discard_event__should_produce_discard_action_for_seat_player():
    discard = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD],
        WireKey.PACKED_MOVE: encode_discard(0, 118, is_tsumogiri=False, is_riichi=False),
    }
    content = _build_records(ROUND_STARTED_RECORD, DRAW_RECORD, discard)
    replay = load_replay_records(content)
    assert replay.seed == _TEST_SEED
    assert set(replay.player_names) == {"Alice", "Bob", "Charlie", "Diana"}
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.DISCARD
    assert replay.events[0].data == {"tile_id": 118}


def test_load_replay__when_discard_has_riichi_flag__should_produce_declare_riichi_action():
    discard = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD],
        WireKey.PACKED_MOVE: encode_discard(1, 50, is_tsumogiri=False, is_riichi=True),
    }
    content = _build_records(discard)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.DECLARE_RIICHI
    assert replay.events[0].data == {"tile_id": 50}


def test_load_replay__when_pon_meld__should_produce_call_pon_action():
    meld = _compact_meld(meld_type="pon", caller_seat=2, from_seat=0, tile_ids=[8, 9, 10], called_tile_id=8)
    content = _build_records(meld)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Charlie"
    assert replay.events[0].action == GameAction.CALL_PON
    assert replay.events[0].data == {"tile_id": 8}


def test_load_replay__when_chi_meld__should_produce_call_chi_action_with_sequence_tiles():
    meld = _compact_meld(meld_type="chi", caller_seat=1, from_seat=0, tile_ids=[20, 24, 28], called_tile_id=20)
    content = _build_records(meld)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_CHI
    assert replay.events[0].data == {"tile_id": 20, "sequence_tiles": [24, 28]}


def test_load_replay__when_open_kan_meld__should_produce_open_call_kan_action():
    meld = _compact_meld(meld_type="open_kan", caller_seat=3, from_seat=0, tile_ids=[0, 1, 2, 3], called_tile_id=2)
    content = _build_records(meld)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Diana"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 2, "kan_type": "open"}


def test_load_replay__when_closed_kan_meld__should_produce_closed_call_kan_action():
    meld = _compact_meld(
        meld_type="closed_kan", caller_seat=1, from_seat=None, tile_ids=[0, 1, 2, 3], called_tile_id=None
    )
    content = _build_records(meld)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 0, "kan_type": "closed"}


def test_load_replay__when_added_kan_meld__should_produce_added_call_kan_action():
    meld = _compact_meld(
        meld_type="added_kan", caller_seat=0, from_seat=2, tile_ids=[4, 5, 6, 7], called_tile_id=7, added_tile_id=5
    )
    content = _build_records(meld)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.CALL_KAN
    assert replay.events[0].data == {"tile_id": 7, "kan_type": "added"}


def test_load_replay__when_round_ends_in_tsumo__should_produce_declare_tsumo_action():
    round_end = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END],
        WireKey.RESULT_TYPE: WireRoundResultType.TSUMO,
        WireKey.WINNER_SEAT: 2,
        WireKey.SCORE_CHANGES: {},
    }
    content = _build_records(round_end)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Charlie"
    assert replay.events[0].action == GameAction.DECLARE_TSUMO


def test_load_replay__when_round_ends_in_ron__should_produce_call_ron_action():
    round_end = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END],
        WireKey.RESULT_TYPE: WireRoundResultType.RON,
        WireKey.WINNER_SEAT: 1,
        WireKey.LOSER_SEAT: 0,
    }
    content = _build_records(round_end)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Bob"
    assert replay.events[0].action == GameAction.CALL_RON


def test_load_replay__when_round_ends_in_double_ron__should_produce_call_ron_for_each_winner():
    round_end = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END],
        WireKey.RESULT_TYPE: WireRoundResultType.DOUBLE_RON,
        WireKey.LOSER_SEAT: 0,
        WireKey.WINNERS: [{WireKey.WINNER_SEAT: 3}, {WireKey.WINNER_SEAT: 1}],
    }
    content = _build_records(round_end)
    replay = load_replay_records(content)
    assert len(replay.events) == 2
    assert replay.events[0].player_name == "Diana"
    assert replay.events[0].action == GameAction.CALL_RON
    assert replay.events[1].player_name == "Bob"
    assert replay.events[1].action == GameAction.CALL_RON


def test_load_replay__when_round_ends_in_nine_terminals__should_produce_call_kyuushu_action():
    round_end = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END],
        WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
        WireKey.ABORTIVE_REASON: "nine_terminals",
        WireKey.SEAT: 0,
    }
    content = _build_records(round_end)
    replay = load_replay_records(content)
    assert len(replay.events) == 1
    assert replay.events[0].player_name == "Alice"
    assert replay.events[0].action == GameAction.CALL_KYUUSHU


def test_load_replay__when_round_ends_without_player_action__should_produce_no_actions():
    cases = [
        (WireRoundResultType.ABORTIVE_DRAW, {WireKey.ABORTIVE_REASON: "four_riichi"}),
        (WireRoundResultType.EXHAUSTIVE_DRAW, {WireKey.TENPAI_SEATS: [], WireKey.NOTEN_SEATS: []}),
        (WireRoundResultType.NAGASHI_MANGAN, {}),
    ]
    for rt, extra_fields in cases:
        round_end = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END], WireKey.RESULT_TYPE: rt, **extra_fields}
        content = _build_records(round_end)
        replay = load_replay_records(content)
        assert len(replay.events) == 0, f"Expected no events for round_end type {rt}"


def test_load_replay__when_events_are_not_player_actions__should_skip_them():
    content = _build_records(
        ROUND_STARTED_RECORD,
        DRAW_RECORD,
        {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DORA_REVEALED], WireKey.TILE_ID: 54},
        {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.RIICHI_DECLARED], WireKey.SEAT: 0},
        {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_END], "result": {}},
        {
            WireKey.EVENT_TYPE: ReplayLineType.SEAT_CONTROL,
            WireKey.SEAT: 0,
            WireKey.AI_PLAYER: 1,
            WireKey.RIICHI_STICKS: SeatControlReason.LEFT,
        },
        {WireKey.EVENT_TYPE: ReplayLineType.SEAT_CONTROL, WireKey.SEAT: 0, WireKey.AI_PLAYER: 0},
    )
    replay = load_replay_records(content)
    assert len(replay.events) == 0


def test_load_replay__when_version_tag_missing__should_raise():
    content = [GAME_STARTED_RECORD]
    with pytest.raises(ReplayLoadError, match="must contain at least a version tag"):
        load_replay_records(content)


def test_load_replay__when_version_mismatches__should_raise():
    bad_version = {WireKey.REPLAY_VERSION: "99.0"}
    content = [bad_version, GAME_STARTED_RECORD]
    with pytest.raises(ReplayLoadError, match="Replay version mismatch"):
        load_replay_records(content)


def test_load_replay__when_first_line_has_no_version_field__should_raise():
    no_version = {"something": "else"}
    content = [no_version, GAME_STARTED_RECORD]
    with pytest.raises(ReplayLoadError, match="must be a version tag"):
        load_replay_records(content)


def test_load_replay__when_first_event_is_not_game_started__should_raise():
    round_started = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_STARTED], "view": {}}
    content = [VERSION_RECORD, round_started]
    with pytest.raises(ReplayLoadError, match="First event must be game_started"):
        load_replay_records(content)


def test_load_replay_from_bytes__when_record_is_incomplete__should_report_decode_failure():
    with pytest.raises(ReplayLoadError, match="Cannot decode replay"):
        load_replay_from_bytes(b"\x81")


def test_load_replay__when_rng_version_missing__should_raise():
    no_version = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.PLAYERS: [
            {WireKey.SEAT: 0, WireKey.NAME: "A", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 1, WireKey.NAME: "B", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 2, WireKey.NAME: "C", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 3, WireKey.NAME: "D", WireKey.AI_PLAYER: 0},
        ],
    }
    with pytest.raises(ReplayLoadError, match="missing 'rv' field"):
        load_replay_records([VERSION_RECORD, no_version])


def test_load_replay__when_rng_version_mismatches__should_raise():
    bad_version = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: "old-version-v0",
        WireKey.PLAYERS: [
            {WireKey.SEAT: 0, WireKey.NAME: "A", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 1, WireKey.NAME: "B", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 2, WireKey.NAME: "C", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 3, WireKey.NAME: "D", WireKey.AI_PLAYER: 0},
        ],
    }
    with pytest.raises(ReplayLoadError, match="RNG version mismatch"):
        load_replay_records([VERSION_RECORD, bad_version])


def test_load_replay__when_seed_missing__should_raise():
    no_seed = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.PLAYERS: [
            {WireKey.SEAT: 0, WireKey.NAME: "A"},
            {WireKey.SEAT: 1, WireKey.NAME: "B"},
            {WireKey.SEAT: 2, WireKey.NAME: "C"},
            {WireKey.SEAT: 3, WireKey.NAME: "D"},
        ],
    }
    with pytest.raises(ReplayLoadError, match="missing 'sd' field"):
        load_replay_records([VERSION_RECORD, no_seed])


@pytest.mark.parametrize("seed", ["not-hex-seed" + "0" * 180, 12345])
def test_load_replay__when_seed_is_not_a_hex_string__should_raise(seed: str | int):
    bad_seed = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: seed,
        WireKey.RNG_VERSION: RNG_VERSION,
        WireKey.PLAYERS: [
            {WireKey.SEAT: 0, WireKey.NAME: "A", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 1, WireKey.NAME: "B", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 2, WireKey.NAME: "C", WireKey.AI_PLAYER: 0},
            {WireKey.SEAT: 3, WireKey.NAME: "D", WireKey.AI_PLAYER: 0},
        ],
    }
    with pytest.raises(ReplayLoadError, match="invalid seed"):
        load_replay_records([VERSION_RECORD, bad_seed])


def test_load_replay__when_event_type_unknown__should_raise():
    content = _build_records({WireKey.EVENT_TYPE: 999})
    with pytest.raises(ReplayLoadError, match="Unknown event type"):
        load_replay_records(content)


def test_load_replay__when_event_type_missing__should_raise():
    content = _build_records({WireKey.SEAT: 0, WireKey.TILE_ID: 10})
    with pytest.raises(ReplayLoadError, match="Event missing required 't' field"):
        load_replay_records(content)


def test_load_replay__when_content_is_empty__should_raise():
    with pytest.raises(ReplayLoadError, match="must contain at least"):
        load_replay_records([])


def test_load_replay_from_file__when_raw_messagepack_file__should_load_replay(tmp_path: Path):
    discard = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD],
        WireKey.PACKED_MOVE: encode_discard(0, 118, is_tsumogiri=False, is_riichi=False),
    }
    content = _build_records(discard)
    file_path = tmp_path / "test.msgpack"
    file_path.write_bytes(encode_replay_records(content))
    replay = load_replay_from_file(file_path)
    assert replay.seed == _TEST_SEED
    assert len(replay.events) == 1


def test_load_replay_from_file__when_gzip_file__should_load_replay(tmp_path: Path):
    discard = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD],
        WireKey.PACKED_MOVE: encode_discard(0, 118, is_tsumogiri=False, is_riichi=False),
    }
    content = _build_records(discard)
    file_path = tmp_path / "test.msgpack.gz"
    file_path.write_bytes(gzip.compress(encode_replay_records(content)))
    replay = load_replay_from_file(file_path)
    assert replay.seed == _TEST_SEED
    assert len(replay.events) == 1


def test_load_replay_from_file__when_file_unreadable__should_raise():
    with pytest.raises(ReplayLoadError, match="Cannot read replay file"):
        load_replay_from_file("/nonexistent/path/replay.msgpack")


def test_load_replay_from_file__when_gzip_is_corrupted__should_raise(tmp_path: Path):
    file_path = tmp_path / "corrupted.msgpack.gz"
    file_path.write_bytes(b"not valid gzip data at all")
    with pytest.raises(ReplayLoadError, match="Cannot read replay file"):
        load_replay_from_file(file_path)


def test_load_replay__when_players_missing__should_raise():
    no_players = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: RNG_VERSION,
    }
    with pytest.raises(ReplayLoadError, match="missing 'p' field"):
        load_replay_records([VERSION_RECORD, no_players])


def test_load_replay__when_round_end_result_type_unknown__should_raise():
    round_end = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END], WireKey.RESULT_TYPE: 99}
    content = _build_records(round_end)
    with pytest.raises(ReplayLoadError, match="Unknown round_end result type"):
        load_replay_records(content)


def test_load_replay__when_discard_missing_packed_value__should_raise():
    discard = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD]}
    content = _build_records(discard)
    with pytest.raises(ReplayLoadError, match="discard event missing 'd' field"):
        load_replay_records(content)


def test_load_replay__when_discard_packed_value_invalid__should_raise():
    discard = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD], WireKey.PACKED_MOVE: 9999}
    content = _build_records(discard)
    with pytest.raises(ReplayLoadError, match="Invalid discard packed value"):
        load_replay_records(content)


def test_load_replay__when_meld_missing_compact_value__should_raise():
    meld = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.MELD]}
    content = _build_records(meld)
    with pytest.raises(ReplayLoadError, match="Compact meld event missing 'm' field"):
        load_replay_records(content)


def test_load_replay__when_meld_compact_value_corrupt__should_raise():
    meld = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.MELD], WireKey.PACKED_MELD: 999999}
    content = _build_records(meld)
    with pytest.raises(ReplayLoadError, match="Invalid compact meld value"):
        load_replay_records(content)


def test_load_replay__when_discard_references_unknown_seat__should_raise(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(replay_loader_module, "decode_discard", lambda _d: (9, 0, False, False))
    discard = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD], WireKey.PACKED_MOVE: 0}
    content = _build_records(discard)
    with pytest.raises(ReplayLoadError, match="discard event references unknown seat"):
        load_replay_records(content)


def test_load_replay__when_meld_references_unknown_seat__should_raise(monkeypatch: pytest.MonkeyPatch):
    fake_meld_data = MeldData(
        type="meld",
        meld_type="pon",
        caller_seat=9,
        from_seat=0,
        tile_ids=[0, 1, 2],
        called_tile_id=0,
        added_tile_id=None,
    )
    monkeypatch.setattr(replay_loader_module, "decode_meld_compact", lambda _v: fake_meld_data)
    meld = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.MELD], WireKey.PACKED_MELD: 0}
    content = _build_records(meld)
    with pytest.raises(ReplayLoadError, match="meld event references unknown seat"):
        load_replay_records(content)


def test_load_replay__when_meld_type_unknown__should_raise(monkeypatch: pytest.MonkeyPatch):
    fake_meld_data = MeldData(
        type="meld",
        meld_type="bogus",
        caller_seat=0,
        from_seat=1,
        tile_ids=[0, 1, 2],
        called_tile_id=0,
        added_tile_id=None,
    )
    monkeypatch.setattr(replay_loader_module, "decode_meld_compact", lambda _v: fake_meld_data)
    meld = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.MELD], WireKey.PACKED_MELD: 0}
    content = _build_records(meld)
    with pytest.raises(ReplayLoadError, match="Unknown meld_type in decoded IMME"):
        load_replay_records(content)


def test_load_replay__when_player_seats_are_not_0_to_3__should_raise():
    bad_started = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: RNG_VERSION,
        WireKey.PLAYERS: [
            {WireKey.SEAT: 0, WireKey.NAME: "A"},
            {WireKey.SEAT: 1, WireKey.NAME: "B"},
            {WireKey.SEAT: 2, WireKey.NAME: "C"},
            {WireKey.SEAT: 5, WireKey.NAME: "D"},
        ],
    }
    with pytest.raises(ReplayLoadError, match="must have exactly seats"):
        load_replay_records([VERSION_RECORD, bad_started])


_ROUND_END = EVENT_TYPE_INT[EventType.ROUND_END]
_RON_BY_BOB = {
    WireKey.EVENT_TYPE: _ROUND_END,
    WireKey.RESULT_TYPE: WireRoundResultType.RON,
    WireKey.WINNER_SEAT: 1,
    WireKey.LOSER_SEAT: 0,
}
_MISSING = object()


@pytest.mark.parametrize(
    "round_end",
    [
        pytest.param(
            {WireKey.EVENT_TYPE: _ROUND_END, WireKey.RESULT_TYPE: WireRoundResultType.TSUMO}, id="tsumo_missing"
        ),
        pytest.param({**_RON_BY_BOB, WireKey.WINNER_SEAT: True}, id="ron_bool"),
        pytest.param({**_RON_BY_BOB, WireKey.WINNER_SEAT: 1.0}, id="ron_float"),
        pytest.param({**_RON_BY_BOB, WireKey.WINNER_SEAT: 7}, id="ron_unknown"),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.DOUBLE_RON,
                WireKey.LOSER_SEAT: 0,
                WireKey.WINNERS: [{"some_field": 1}],
            },
            id="double_ron_winner_missing",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
                WireKey.ABORTIVE_REASON: "nine_terminals",
            },
            id="nine_terminals_missing",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
                WireKey.ABORTIVE_REASON: "triple_ron",
                WireKey.RON_CALLERS: [True, 2, 3],
            },
            id="triple_ron_bool",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
                WireKey.ABORTIVE_REASON: "triple_ron",
                WireKey.RON_CALLERS: [1, 2, "3"],
            },
            id="triple_ron_string",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
                WireKey.ABORTIVE_REASON: "triple_ron",
                WireKey.RON_CALLERS: [1, 2, 7],
            },
            id="triple_ron_unknown",
        ),
        pytest.param(
            {**_RON_BY_BOB, WireKey.ROBBED_KAN: {WireKey.SEAT: True, WireKey.TILE_ID: 47, WireKey.KAN_TYPE: "added"}},
            id="robbed_kan_bool",
        ),
        pytest.param(
            {**_RON_BY_BOB, WireKey.ROBBED_KAN: {WireKey.SEAT: 0.0, WireKey.TILE_ID: 47, WireKey.KAN_TYPE: "added"}},
            id="robbed_kan_float",
        ),
        pytest.param({**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: [True]}, id="head_bumped_bool"),
        pytest.param({**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: [7]}, id="head_bumped_unknown"),
    ],
)
def test_load_replay__when_round_end_seat_malformed__should_raise(round_end: dict[int, object]):
    content = _build_records(round_end)
    with pytest.raises(ReplayLoadError, match="is not a known seat"):
        load_replay_records(content)


@pytest.mark.parametrize(
    ("winners", "error"),
    [
        pytest.param(_MISSING, "must have a non-empty winner list", id="missing"),
        pytest.param([], "must have a non-empty winner list", id="empty"),
        pytest.param(5, "must have a non-empty winner list", id="not_a_list"),
        pytest.param([5], "winner must be an object", id="winner_not_an_object"),
    ],
)
def test_load_replay__when_double_ron_winners_malformed__should_raise(winners: object, error: str):
    round_end: dict[int, object] = {
        WireKey.EVENT_TYPE: _ROUND_END,
        WireKey.RESULT_TYPE: WireRoundResultType.DOUBLE_RON,
        WireKey.LOSER_SEAT: 0,
    }
    if winners is not _MISSING:
        round_end[WireKey.WINNERS] = winners
    content = _build_records(round_end)
    with pytest.raises(ReplayLoadError, match=error):
        load_replay_records(content)


@pytest.mark.parametrize(
    "ron_seats",
    [
        pytest.param(_MISSING, id="missing"),
        pytest.param(None, id="null"),
        pytest.param([], id="empty"),
        pytest.param(1, id="not_a_list"),
        pytest.param([1, 2], id="too_few"),
        pytest.param([0, 1, 2, 3], id="too_many"),
        pytest.param([1, 1, 2], id="duplicate"),
    ],
)
def test_load_replay__when_triple_ron_ron_seats_malformed__should_raise(ron_seats: object):
    round_end: dict[int, object] = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.ROUND_END],
        WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
        WireKey.ABORTIVE_REASON: "triple_ron",
    }
    if ron_seats is not _MISSING:
        round_end[WireKey.RON_CALLERS] = ron_seats
    content = _build_records(round_end)
    with pytest.raises(ReplayLoadError, match="triple_ron abortive_draw has invalid ron seats"):
        load_replay_records(content)


@pytest.mark.parametrize(
    "robbed_kan",
    [
        pytest.param("added", id="not_an_object"),
        pytest.param({WireKey.SEAT: 0, WireKey.TILE_ID: 47}, id="missing_kan_type"),
        pytest.param({WireKey.SEAT: 0, WireKey.TILE_ID: True, WireKey.KAN_TYPE: "added"}, id="bool_tile"),
        pytest.param({WireKey.SEAT: 0, WireKey.TILE_ID: -1, WireKey.KAN_TYPE: "added"}, id="negative_tile"),
        pytest.param({WireKey.SEAT: 0, WireKey.TILE_ID: 136, WireKey.KAN_TYPE: "added"}, id="tile_past_the_last"),
        pytest.param({WireKey.SEAT: 0, WireKey.TILE_ID: 47, WireKey.KAN_TYPE: "open"}, id="open_kan"),
        pytest.param({WireKey.SEAT: 0, WireKey.TILE_ID: 47, WireKey.KAN_TYPE: "pon"}, id="unknown_kan_type"),
    ],
)
def test_load_replay__when_robbed_kan_malformed__should_raise(robbed_kan: object):
    content = _build_records({**_RON_BY_BOB, WireKey.ROBBED_KAN: robbed_kan})
    with pytest.raises(ReplayLoadError, match="invalid robbed kan \\(rk\\)"):
        load_replay_records(content)


@pytest.mark.parametrize(
    "round_end",
    [
        pytest.param(
            {WireKey.EVENT_TYPE: _ROUND_END, WireKey.RESULT_TYPE: WireRoundResultType.TSUMO, WireKey.WINNER_SEAT: 1},
            id="tsumo",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.ABORTIVE_DRAW,
                WireKey.ABORTIVE_REASON: "four_kans",
            },
            id="four_kans",
        ),
        pytest.param(
            {WireKey.EVENT_TYPE: _ROUND_END, WireKey.RESULT_TYPE: WireRoundResultType.EXHAUSTIVE_DRAW},
            id="exhaustive_draw",
        ),
    ],
)
def test_load_replay__when_round_end_that_robs_no_kan_carries_one__should_raise(round_end: dict[int, object]):
    robbed_kan = {WireKey.SEAT: 0, WireKey.TILE_ID: 47, WireKey.KAN_TYPE: "added"}
    content = _build_records({**round_end, WireKey.ROBBED_KAN: robbed_kan})
    with pytest.raises(ReplayLoadError, match="robs no kan carries a robbed kan \\(rk\\)"):
        load_replay_records(content)


@pytest.mark.parametrize(
    ("round_end", "error"),
    [
        pytest.param(
            {**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: 2}, "invalid head-bumped ron seats \\(hbs\\)", id="not_a_list"
        ),
        pytest.param(
            {**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: []}, "invalid head-bumped ron seats \\(hbs\\)", id="empty"
        ),
        pytest.param(
            {**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: [2, 2]},
            "invalid head-bumped ron seats \\(hbs\\)",
            id="duplicate",
        ),
        pytest.param(
            {**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: [1]}, "invalid head-bumped ron seats \\(hbs\\)", id="the_winner"
        ),
        pytest.param(
            {**_RON_BY_BOB, WireKey.HEAD_BUMPED_SEATS: [0]},
            "invalid head-bumped ron seats \\(hbs\\)",
            id="the_discarder",
        ),
        pytest.param(
            {
                **_RON_BY_BOB,
                WireKey.ROBBED_KAN: {WireKey.SEAT: 3, WireKey.TILE_ID: 47, WireKey.KAN_TYPE: "added"},
                WireKey.HEAD_BUMPED_SEATS: [3],
            },
            "invalid head-bumped ron seats \\(hbs\\)",
            id="the_robbed_kan_declarer",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.DOUBLE_RON,
                WireKey.LOSER_SEAT: 0,
                WireKey.WINNERS: [{WireKey.WINNER_SEAT: 1}, {WireKey.WINNER_SEAT: 2}],
                WireKey.HEAD_BUMPED_SEATS: [2],
            },
            "invalid head-bumped ron seats \\(hbs\\)",
            id="a_double_ron_winner",
        ),
        pytest.param(
            {
                WireKey.EVENT_TYPE: _ROUND_END,
                WireKey.RESULT_TYPE: WireRoundResultType.TSUMO,
                WireKey.WINNER_SEAT: 1,
                WireKey.HEAD_BUMPED_SEATS: [2],
            },
            "is no ron carries head-bumped ron seats \\(hbs\\)",
            id="on_a_tsumo",
        ),
    ],
)
def test_load_replay__when_head_bumped_ron_seats_malformed__should_raise(round_end: dict[int, object], error: str):
    content = _build_records(round_end)
    with pytest.raises(ReplayLoadError, match=error):
        load_replay_records(content)


_DEFAULT_SETTINGS = encode_replay_settings(GameSettings())


@pytest.mark.parametrize(
    ("game_started", "error"),
    [
        pytest.param({**GAME_STARTED, WireKey.GAME_SETTINGS: _MISSING}, "invalid settings", id="missing"),
        pytest.param({**GAME_STARTED, WireKey.GAME_SETTINGS: "hanchan"}, "invalid settings", id="not_an_object"),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_SETTINGS: {k: v for k, v in _DEFAULT_SETTINGS.items() if k != "overrides"}},
            "invalid settings",
            id="missing_field",
        ),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_SETTINGS: {**_DEFAULT_SETTINGS, "overrides": {"has_sanma": True}}},
            "invalid settings",
            id="extra",
        ),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_SETTINGS: {**_DEFAULT_SETTINGS, "overrides": {"riichi_cost": "1000"}}},
            "invalid settings",
            id="type",
        ),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_SETTINGS: {**_DEFAULT_SETTINGS, "overrides": {"has_kuitan": 1}}},
            "invalid settings",
            id="int_bool",
        ),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_SETTINGS: {**_DEFAULT_SETTINGS, "overrides": {"has_agariyame": True}}},
            "invalid settings",
            id="unsupported",
        ),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_TYPE: 1}, "game type \\(gt\\) 1 does not match", id="game_type_mismatch"
        ),
        pytest.param(
            {**GAME_STARTED, WireKey.GAME_TYPE: False}, "game type \\(gt\\) False does not match", id="game_type_bool"
        ),
        pytest.param(
            {k: v for k, v in GAME_STARTED.items() if k != WireKey.GAME_TYPE},
            "game type \\(gt\\) None",
            id="game_type_missing",
        ),
    ],
)
def test_load_replay__when_game_settings_malformed__should_raise(game_started: dict[int, object], error: str):
    recorded = {k: v for k, v in game_started.items() if v is not _MISSING}
    with pytest.raises(ReplayLoadError, match=error):
        load_replay_records([VERSION_RECORD, recorded])


def test_load_replay__when_discard_packed_value_is_bool__should_raise():
    discard = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD], WireKey.PACKED_MOVE: True}
    content = _build_records(discard)
    with pytest.raises(ReplayLoadError, match="Invalid discard packed value"):
        load_replay_records(content)


def test_load_replay__when_event_count_exceeds_maximum__should_raise():
    events = [VERSION_RECORD, GAME_STARTED_RECORD]
    filler = {WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DRAW], WireKey.SEAT: 0, WireKey.TILE_ID: 0}
    events.extend([filler] * _MAX_REPLAY_EVENTS)
    content = events
    with pytest.raises(ReplayLoadError, match="maximum event count"):
        load_replay_records(content)


def test_load_replay__when_player_entry_is_not_a_dict__should_raise():
    bad_started = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: RNG_VERSION,
        WireKey.PLAYERS: ["Alice", "Bob", "Charlie", "Diana"],
    }
    with pytest.raises(ReplayLoadError, match="player entry 0 is not a dict"):
        load_replay_records([VERSION_RECORD, bad_started])


def test_load_replay__when_player_entry_missing_seat__should_raise():
    bad_started = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: RNG_VERSION,
        WireKey.PLAYERS: [
            {WireKey.NAME: "A"},
            {WireKey.SEAT: 1, WireKey.NAME: "B"},
            {WireKey.SEAT: 2, WireKey.NAME: "C"},
            {WireKey.SEAT: 3, WireKey.NAME: "D"},
        ],
    }
    with pytest.raises(ReplayLoadError, match="player entry 0 missing required field"):
        load_replay_records([VERSION_RECORD, bad_started])


def test_load_replay__when_player_entry_seat_is_not_integer__should_raise():
    bad_started = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: RNG_VERSION,
        WireKey.PLAYERS: [
            {WireKey.SEAT: "zero", WireKey.NAME: "A"},
            {WireKey.SEAT: 1, WireKey.NAME: "B"},
            {WireKey.SEAT: 2, WireKey.NAME: "C"},
            {WireKey.SEAT: 3, WireKey.NAME: "D"},
        ],
    }
    with pytest.raises(ReplayLoadError, match="non-integer seat"):
        load_replay_records([VERSION_RECORD, bad_started])


def test_load_replay__when_event_type_is_bool__should_raise():
    content = _build_records({WireKey.EVENT_TYPE: True, WireKey.SEAT: 0, WireKey.TILE_ID: 5})
    with pytest.raises(ReplayLoadError, match="'t' field must be an integer"):
        load_replay_records(content)


def test_load_replay__when_meld_value_is_bool__should_raise():
    content = _build_records({WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.MELD], WireKey.PACKED_MELD: True})
    with pytest.raises(ReplayLoadError, match="'m' field must be an integer"):
        load_replay_records(content)


def test_load_replay__when_player_entry_name_is_empty__should_raise():
    bad_started = {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.GAME_STARTED],
        WireKey.GAME_ID: "test",
        WireKey.SEED: _TEST_SEED,
        WireKey.RNG_VERSION: RNG_VERSION,
        WireKey.PLAYERS: [
            {WireKey.SEAT: 0, WireKey.NAME: ""},
            {WireKey.SEAT: 1, WireKey.NAME: "B"},
            {WireKey.SEAT: 2, WireKey.NAME: "C"},
            {WireKey.SEAT: 3, WireKey.NAME: "D"},
        ],
    }
    with pytest.raises(ReplayLoadError, match="invalid name"):
        load_replay_records([VERSION_RECORD, bad_started])


@pytest.mark.parametrize("compressed", [False, True])
def test_load_replay_from_file__when_payload_exceeds_limit__should_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, compressed: bool
):
    limit = 8
    monkeypatch.setattr(replay_loader_module, "MAX_REPLAY_BYTES", limit)
    monkeypatch.setattr(replay_format, "MAX_REPLAY_BYTES", limit)
    content = b"x" * (limit + 1)
    path = tmp_path / ("oversized.msgpack.gz" if compressed else "oversized.msgpack")
    path.write_bytes(gzip.compress(content) if compressed else content)
    with pytest.raises(ReplayLoadError, match="replay exceeds 8 bytes"):
        load_replay_from_file(path)
