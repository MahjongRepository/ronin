from game.logic.enums import CallType, MeldCallType, PromptKind
from game.logic.events import (
    DrawEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
    build_call_prompt_events,
    convert_events,
    extract_round_result,
)
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.logic.types import (
    HandResultInfo,
    MeldCaller,
    RoundResultType,
    TsumoResult,
    YakuInfo,
)
from game.tests.unit.helpers import _string_to_136_tile


class TestConvertEvents:
    def test_convert_events__when_typed_event__should_wrap_in_service_event(self):
        events = [DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target=SeatTarget(seat=0))]

        result = convert_events(events)
        assert len(result) == 1
        assert isinstance(result[0], ServiceEvent)
        assert result[0].event == EventType.DRAW
        assert isinstance(result[0].data, DrawEvent)
        assert result[0].data.seat == 0
        assert result[0].target == SeatTarget(seat=0)


class TestBuildCallPromptEvents:
    def test_build_call_prompt_events__when_discard_prompt_mixes_ron_and_meld__should_emit_one_event_per_caller(self):
        chi_shape = (57, 63)
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=55,
            from_seat=0,
            pending_seats=frozenset({1, 3}),
            callers=(
                Caller(seat=3, can_ron=True),
                Caller(
                    seat=1,
                    melds=(
                        MeldOption(call_type=MeldCallType.PON),
                        MeldOption(call_type=MeldCallType.CHI, options=(chi_shape,)),
                    ),
                ),
            ),
        )

        events = build_call_prompt_events(prompt)
        assert [(e.target, e.call_type, e.tile_id, e.from_seat) for e in events] == [
            (SeatTarget(seat=3), CallType.RON, 55, 0),
            (SeatTarget(seat=1), CallType.MELD, 55, 0),
        ]
        assert events[0].callers == [3]
        assert events[1].callers == [
            MeldCaller(seat=1, call_type=MeldCallType.PON),
            MeldCaller(seat=1, call_type=MeldCallType.CHI, options=(chi_shape,)),
        ]

    def test_build_call_prompt_events__when_chankan_prompt__should_emit_chankan_event_per_caller(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.CHANKAN,
            tile_id=10,
            from_seat=2,
            pending_seats=frozenset({0, 1}),
            callers=(Caller(seat=0, can_ron=True), Caller(seat=1, can_ron=True)),
        )

        events = build_call_prompt_events(prompt)
        assert [(e.target, e.call_type, e.callers) for e in events] == [
            (SeatTarget(seat=0), CallType.CHANKAN, [0]),
            (SeatTarget(seat=1), CallType.CHANKAN, [1]),
        ]


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
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target=SeatTarget(seat=0)),
            ),
            ServiceEvent(
                data=RoundEndEvent(result=tsumo_result),
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
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target=SeatTarget(seat=0)),
            ),
            ServiceEvent(
                data=DrawEvent(seat=0, tile_id=_string_to_136_tile(man="1"), target=SeatTarget(seat=0)),
            ),
        ]

        result = extract_round_result(events)
        assert result is None
