import pytest
from pydantic import ValidationError

from game.logic.enums import CallType, KanType, MeldCallType, PromptKind
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

    def test_build_call_prompt_events__when_chankan_prompt__should_emit_chankan_event_per_caller_naming_the_kan(self):
        prompt = PendingCallPrompt(
            kind=PromptKind.CHANKAN,
            tile_id=10,
            from_seat=2,
            pending_seats=frozenset({0, 1}),
            callers=(Caller(seat=0, can_ron=True), Caller(seat=1, can_ron=True)),
            kan_type=KanType.ADDED,
        )

        events = build_call_prompt_events(prompt)
        assert [(e.target, e.call_type, e.callers, e.kan_type) for e in events] == [
            (SeatTarget(seat=0), CallType.CHANKAN, [0], KanType.ADDED),
            (SeatTarget(seat=1), CallType.CHANKAN, [1], KanType.ADDED),
        ]

    def test_pending_call_prompt__when_kan_type_does_not_match_the_prompt_kind__should_raise(self):
        with pytest.raises(ValidationError, match="names the kan it offers to rob"):
            PendingCallPrompt(
                kind=PromptKind.CHANKAN,
                tile_id=10,
                from_seat=2,
                pending_seats=frozenset({0}),
                callers=(Caller(seat=0, can_ron=True),),
            )
