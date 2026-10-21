from game.logic.call_resolution import (
    pick_best_meld_response,
)
from game.logic.enums import (
    CallType,
    GameAction,
    MeldCallType,
)
from game.logic.state import (
    CallResponse,
    PendingCallPrompt,
)
from game.logic.types import MeldCaller


class TestPickBestMeldResponseTieBreak:
    def test_pick_best_meld_response__when_distance_wraps_around_table__should_prefer_closest_seat(self):
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=2,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=0, call_type=MeldCallType.PON),
                MeldCaller(seat=3, call_type=MeldCallType.PON),
            ),
        )
        responses = [
            CallResponse(seat=0, action=GameAction.CALL_PON),
            CallResponse(seat=3, action=GameAction.CALL_PON),
        ]
        best = pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 3  # distance 1 from discarder seat 2
