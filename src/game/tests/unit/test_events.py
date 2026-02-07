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

from game.logic.types import (
    HandResultInfo,
    RoundResultType,
    TsumoResult,
)
from game.messaging.events import (
    DrawEvent,
    EventType,
    RoundEndEvent,
    ServiceEvent,
    _normalize_event_value,
    convert_events,
    extract_round_result,
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
        assert result[0].target == "seat_0"


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
            ),
            ServiceEvent(event=EventType.ROUND_END, data=RoundEndEvent(result=tsumo_result, target="all")),
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
            ),
            ServiceEvent(
                event=EventType.DRAW,
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0"),
            ),
        ]

        result = extract_round_result(events)

        assert result is None
