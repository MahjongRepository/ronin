"""
Tests for deterministic meld response tie-breaking.

Verifies that pick_best_meld_response uses counter-clockwise seat distance
from the discarder as a stable tie-breaker when the discarder is not at seat 0.
"""

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
    """Verify pick_best_meld_response wrapping distance when discarder != seat 0."""

    def test_wrapping_distance_calculation(self):
        """Distance wraps around: discarder seat 2, seat 3 is distance 1, seat 0 is distance 2."""
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
