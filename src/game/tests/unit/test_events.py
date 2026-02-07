"""
Tests for game event utility functions and validation.

Constructor tests for individual event types (DrawEvent, DiscardEvent, MeldEvent,
TurnEvent, CallPromptEvent, RoundEndEvent, RiichiDeclaredEvent, DoraRevealedEvent,
ErrorEvent) and model_dump serialization tests were removed: they tested only
Pydantic field assignment and built-in model_dump, which Pydantic guarantees.

Kept: _normalize_event_value edge case, ServiceEvent validation logic,
convert_events utility, extract_round_result utility (happy path + None path).
"""

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
    _normalize_event_value,
    convert_events,
    extract_round_result,
    parse_wire_target,
)
from game.logic.types import (
    HandResultInfo,
    MeldCaller,
    RoundResultType,
    TsumoResult,
)
from game.tests.unit.helpers import _string_to_136_tile


def test_normalize_event_value_accepts_string() -> None:
    assert _normalize_event_value("draw") == "draw"


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
        call_prompt = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=42,
            from_seat=3,
            callers=[0, 1],
            target="all",
        )

        result = convert_events([call_prompt])

        assert len(result) == 2
        assert result[0].target == SeatTarget(seat=0)
        assert result[1].target == SeatTarget(seat=1)
        # both wrappers share the same event data
        assert result[0].data is result[1].data
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
        assert result[0].event == EventType.CALL_PROMPT


class TestExtractRoundResult:
    def test_extract_round_result_finds_result(self):
        """extract_round_result extracts result from round_end event."""
        tsumo_result = TsumoResult(
            winner_seat=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["tanyao"]),
            score_changes={0: 1000},
            riichi_sticks_collected=0,
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
