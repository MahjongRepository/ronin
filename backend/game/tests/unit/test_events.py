"""Tests for game event utility functions and validation."""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import CallType, MeldCallType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
    _split_discard_prompt_for_seat,
    convert_events,
    extract_round_result,
    parse_wire_target,
)
from game.logic.types import (
    HandResultInfo,
    MeldCaller,
    RoundResultType,
    TsumoResult,
    YakuInfo,
)
from game.tests.unit.helpers import _string_to_136_tile


class TestServiceEvent:
    def test_event_mismatch_raises(self) -> None:
        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        with pytest.raises(ValueError, match=r"does not match data\.type"):
            ServiceEvent(
                event=EventType.DISCARD,
                data=DrawEvent(seat=0, tile_id=tile_id, target="seat_0"),
            )


class TestParseWireTarget:
    def test_broadcast_target(self) -> None:
        result = parse_wire_target("all")
        assert isinstance(result, BroadcastTarget)

    def test_seat_targets(self) -> None:
        for seat in range(4):
            result = parse_wire_target(f"seat_{seat}")
            assert isinstance(result, SeatTarget)
            assert result.seat == seat

    def test_invalid_target_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid target value"):
            parse_wire_target("bogus")

    def test_negative_seat_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid seat number"):
            parse_wire_target("seat_-1")


class TestConvertEvents:
    def test_convert_events_handles_typed_events(self):
        """convert_events converts typed events to ServiceEvent format."""
        events = [DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0")]

        result = convert_events(events)

        assert len(result) == 1
        assert isinstance(result[0], ServiceEvent)
        assert result[0].event == EventType.DRAW
        assert isinstance(result[0].data, DrawEvent)
        assert result[0].data.seat == 0
        assert result[0].target == SeatTarget(seat=0)

    def test_convert_events_splits_call_prompt_per_seat(self):
        """convert_events splits a CallPromptEvent with 2 callers into 2 per-seat ServiceEvents."""
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=1, call_type=MeldCallType.PON),
        ]
        call_prompt = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=42,
            from_seat=3,
            callers=callers,
            target="all",
        )

        result = convert_events([call_prompt])

        assert len(result) == 2
        assert result[0].target == SeatTarget(seat=0)
        assert result[1].target == SeatTarget(seat=1)
        # each wrapper carries a distinct event copy (no shared mutable data)
        assert result[0].data is not result[1].data
        # callers filtered to each seat's entries
        assert isinstance(result[0].data, CallPromptEvent)
        assert isinstance(result[1].data, CallPromptEvent)
        assert result[0].data.callers == [MeldCaller(seat=0, call_type=MeldCallType.PON)]
        assert result[1].data.callers == [MeldCaller(seat=1, call_type=MeldCallType.PON)]
        assert result[0].event == EventType.CALL_PROMPT

    def test_convert_events_deduplicates_meld_callers(self):
        """convert_events deduplicates MeldCaller entries for the same seat."""
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=0, call_type=MeldCallType.CHI, options=((57, 63),)),
        ]
        call_prompt = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=55,
            from_seat=3,
            callers=callers,
            target="all",
        )

        result = convert_events([call_prompt])

        assert len(result) == 1
        assert result[0].target == SeatTarget(seat=0)
        # both call options preserved for the same seat
        assert isinstance(result[0].data, CallPromptEvent)
        assert result[0].data.callers == callers

    def test_convert_events_single_caller_call_prompt(self):
        """convert_events produces a single per-seat ServiceEvent for a single-caller CallPromptEvent."""
        call_prompt = CallPromptEvent(
            call_type=CallType.RON,
            tile_id=10,
            from_seat=2,
            callers=[1],
            target="all",
        )

        result = convert_events([call_prompt])

        assert len(result) == 1
        assert result[0].target == SeatTarget(seat=1)
        assert isinstance(result[0].data, CallPromptEvent)
        assert result[0].data.callers == [1]
        assert result[0].event == EventType.CALL_PROMPT

    def test_convert_events_splits_discard_prompt_per_seat(self):
        """DISCARD prompt with mixed ron + meld callers is split into per-seat RON/MELD events."""
        callers: list = [
            1,  # ron caller (seat 1)
            MeldCaller(seat=2, call_type=MeldCallType.PON),  # meld caller (seat 2)
        ]
        call_prompt = CallPromptEvent(
            call_type=CallType.DISCARD,
            tile_id=42,
            from_seat=0,
            callers=callers,
            target="all",
        )

        result = convert_events([call_prompt])

        assert len(result) == 2
        # seat 1 gets a RON event
        seat1_event = next(se for se in result if se.target == SeatTarget(seat=1))
        assert isinstance(seat1_event.data, CallPromptEvent)
        assert seat1_event.data.call_type == CallType.RON
        assert seat1_event.data.callers == [1]
        # seat 2 gets a MELD event
        seat2_event = next(se for se in result if se.target == SeatTarget(seat=2))
        assert isinstance(seat2_event.data, CallPromptEvent)
        assert seat2_event.data.call_type == CallType.MELD
        assert seat2_event.data.callers == [MeldCaller(seat=2, call_type=MeldCallType.PON)]

    def test_convert_events_discard_prompt_ron_only(self):
        """DISCARD prompt with only ron callers splits correctly."""
        call_prompt = CallPromptEvent(
            call_type=CallType.DISCARD,
            tile_id=10,
            from_seat=3,
            callers=[0, 1],
            target="all",
        )

        result = convert_events([call_prompt])

        assert len(result) == 2
        for se in result:
            assert isinstance(se.data, CallPromptEvent)
            assert se.data.call_type == CallType.RON


class TestSplitDiscardPromptEmptyCallersGuard:
    def test_raises_for_seat_with_no_entries(self) -> None:
        """_split_discard_prompt_for_seat raises ValueError if seat has no ron or meld entries."""
        call_prompt = CallPromptEvent(
            call_type=CallType.DISCARD,
            tile_id=42,
            from_seat=0,
            callers=[1],  # only seat 1 as ron caller
            target="all",
        )
        with pytest.raises(ValueError, match="no ron or meld entries"):
            _split_discard_prompt_for_seat(call_prompt, 2)  # seat 2 has no entries


class TestExtractRoundResult:
    def test_extract_round_result_finds_result(self):
        """extract_round_result extracts result from round_end event."""
        tsumo_result = TsumoResult(
            winner_seat=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)]),
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 1000},
            riichi_sticks_collected=0,
            closed_tiles=[0, 1, 2, 3],
            melds=[],
            win_tile=3,
        )
        events = [
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=tsumo_result, target="all"),
                target=BroadcastTarget(),
            ),
        ]

        result = extract_round_result(events)

        assert result is not None
        assert isinstance(result, TsumoResult)
        assert result.type == RoundResultType.TSUMO
        assert result.winner_seat == 0

    def test_extract_round_result_no_round_end(self):
        """extract_round_result returns None when no round_end event."""
        events = [
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
                target=SeatTarget(seat=0),
            ),
        ]

        result = extract_round_result(events)

        assert result is None
