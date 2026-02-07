"""
Tests for deterministic meld response tie-breaking.

Verifies that _pick_best_meld_response uses counter-clockwise seat distance
from the discarder as a stable tie-breaker when multiple responses share the
same call priority.
"""

from game.logic.call_resolution import (
    _pick_best_meld_response,
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
    """Verify _pick_best_meld_response uses seat distance as tie-break."""

    def test_same_priority_picks_closer_seat(self):
        """When two responses have the same call priority, pick the one closer to discarder."""
        # Discarder is seat 0. Seat 1 is distance 1, seat 3 is distance 3.
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=3, call_type=MeldCallType.PON),
            ),
        )
        # Both respond with pon (same priority)
        responses = [
            CallResponse(seat=3, action=GameAction.CALL_PON),
            CallResponse(seat=1, action=GameAction.CALL_PON),
        ]
        best = _pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 1  # closer to discarder in counter-clockwise order

    def test_higher_priority_wins_over_closer_seat(self):
        """Kan (priority 0) beats pon (priority 1) even if pon is closer."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=3, call_type=MeldCallType.OPEN_KAN),
            ),
        )
        responses = [
            CallResponse(seat=1, action=GameAction.CALL_PON),
            CallResponse(seat=3, action=GameAction.CALL_KAN),
        ]
        best = _pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 3  # kan > pon

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
        best = _pick_best_meld_response(responses, prompt)
        assert best is not None
        assert best.seat == 3  # distance 1 from discarder seat 2
