from game.logic.enums import CallType, MeldCallType, PromptKind
from game.logic.events import (
    SeatTarget,
    build_call_prompt_events,
)
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.logic.types import (
    MeldCaller,
)


class TestBuildCallPromptEvents:
    def test_build_call_prompt_events__when_discard_prompt_mixes_ron_and_meld__should_emit_one_event_per_caller(self):
        chi_shape = (57, 63)
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=55,
            from_seat=0,
            pending_seats=frozenset({1, 3}),
            callers=(
                Caller(seat=3, can_ron=True, melds=(MeldOption(call_type=MeldCallType.PON),)),
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
        assert events[0].callers == [MeldCaller(seat=3, call_type=MeldCallType.PON)]
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
