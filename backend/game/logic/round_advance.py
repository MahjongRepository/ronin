"""Manage round advancement confirmation between rounds."""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field

logger = logging.getLogger(__name__)


@dataclass
class PendingRoundAdvance:
    """Track round advancement readiness.

    Semantics: AI player seats are pre-confirmed at creation time (they don't need
    player input). Player seats start unconfirmed and must explicitly confirm.
    ``all_confirmed`` returns True when every player seat has confirmed -- or
    immediately if there are no player seats (all-AI-player game).
    """

    confirmed_seats: set[int] = dataclass_field(default_factory=set)
    required_seats: set[int] = dataclass_field(default_factory=set)

    @property
    def all_confirmed(self) -> bool:
        return self.required_seats.issubset(self.confirmed_seats)


class RoundAdvanceManager:
    """Manage round advancement confirmation state for all games."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingRoundAdvance] = {}

    def is_pending(self, game_id: str) -> bool:
        """Check if a round advance is waiting for confirmations."""
        return game_id in self._pending

    def get_unconfirmed_seats(self, game_id: str) -> set[int]:
        """Return seats that haven't confirmed yet."""
        pending = self._pending.get(game_id)
        if pending is None:
            return set()
        return pending.required_seats - pending.confirmed_seats

    def setup_pending(self, game_id: str, ai_player_seats: set[int]) -> bool:
        """Set up round advance confirmation tracking.

        AI player seats are pre-confirmed (they auto-advance). Player seats must
        explicitly confirm via ``confirm_seat()``.

        Returns True if all seats are already confirmed (all AI players),
        meaning the caller should advance immediately.
        """
        player_seats = {seat for seat in range(4) if seat not in ai_player_seats}
        pending = PendingRoundAdvance(
            confirmed_seats=set(ai_player_seats),
            required_seats=player_seats,
        )
        if pending.all_confirmed:
            # All AI players -- no players to wait for. Don't store stale pending state.
            self._pending.pop(game_id, None)
            return True
        self._pending[game_id] = pending
        return False

    def confirm_seat(self, game_id: str, seat: int) -> bool | None:
        """Record a seat's confirmation.

        Only seats in the required set are accepted. AI player seats and
        out-of-range seats are silently ignored (returns False) to prevent
        invalid data from accumulating in confirmed_seats.

        Returns:
            True if all seats now confirmed (caller should advance the round)
            False if still waiting for others or seat is not required
            None if no pending advance exists (error condition)

        """
        pending = self._pending.get(game_id)
        if pending is None:
            return None
        if seat not in pending.required_seats:
            logger.warning("seat %d is not in required_seats, ignoring", seat)
            return False
        pending.confirmed_seats.add(seat)
        if pending.all_confirmed:
            self._pending.pop(game_id, None)
            return True
        return False

    def is_seat_required(self, game_id: str, seat: int) -> bool:
        """Check if a seat is in the required set for pending advance."""
        pending = self._pending.get(game_id)
        if pending is None:
            return False
        return seat in pending.required_seats

    def cleanup_game(self, game_id: str) -> None:
        """Remove pending state for a game."""
        self._pending.pop(game_id, None)
