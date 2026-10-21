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
    parse_event_target,
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
    def test_service_event__when_event_type_mismatches_data__should_raise_value_error(self) -> None:
        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        with pytest.raises(ValueError, match=r"does not match data\.type"):
            ServiceEvent(
                event=EventType.DISCARD,
                data=DrawEvent(seat=0, tile_id=tile_id, target="seat_0"),
            )


class TestParseEventTarget:
    def test_parse_event_target__when_broadcast__should_return_broadcast_target(self) -> None:
        result = parse_event_target("all")
        assert isinstance(result, BroadcastTarget)

    def test_parse_event_target__when_seat_n__should_return_seat_target(self) -> None:
        for seat in range(4):
            result = parse_event_target(f"seat_{seat}")
            assert isinstance(result, SeatTarget)
            assert result.seat == seat

    def test_parse_event_target__when_invalid_value__should_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="invalid target value"):
            parse_event_target("bogus")

    def test_parse_event_target__when_negative_seat__should_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="invalid seat number"):
            parse_event_target("seat_-1")


class TestConvertEvents:
    def test_convert_events__when_typed_event__should_wrap_in_service_event(self):
        events = [DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_0")]

        result = convert_events(events)

        assert len(result) == 1
        assert isinstance(result[0], ServiceEvent)
        assert result[0].event == EventType.DRAW
        assert isinstance(result[0].data, DrawEvent)
        assert result[0].data.seat == 0
        assert result[0].target == SeatTarget(seat=0)

    def test_convert_events__when_call_prompt_has_several_seats__should_split_per_seat(self):
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

    def test_convert_events__when_seat_has_pon_and_chi_options__should_send_one_prompt_with_both(self):
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

    def test_convert_events__when_call_prompt_has_single_caller__should_target_that_seat(self):
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

    def test_convert_events__when_discard_prompt_mixes_ron_and_meld__should_split_per_seat(self):
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

    def test_convert_events__when_discard_prompt_ron_only__should_emit_ron_prompts(self):
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


class TestConvertEventsTargetValidation:
    def test_convert_events__when_negative_seat_target__should_raise_value_error(self) -> None:
        event = DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="seat_-1")
        with pytest.raises(ValueError, match="invalid seat number"):
            convert_events([event])

    def test_convert_events__when_invalid_target_string__should_raise_value_error(self) -> None:
        event = DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target="bogus")
        with pytest.raises(ValueError, match="invalid target value"):
            convert_events([event])


class TestSplitDiscardPromptEmptyCallersGuard:
    def test_split_discard_prompt__when_seat_has_no_ron_or_meld_entries__should_raise_value_error(self) -> None:
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
    def test_extract_round_result__when_round_end_event__should_return_result(self):
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

    def test_extract_round_result__when_no_round_end_event__should_return_none(self):
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
