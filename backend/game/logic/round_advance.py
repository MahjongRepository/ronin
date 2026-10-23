from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class PendingRoundAdvance:
    """
    A round end waiting for its human seats to confirm the next round.

    required_seats are the seats no AI player held when the round ended: AI seats never confirm. A confirmation from any
    other seat is ignored, and a seat counts once however often it confirms.
    """

    required_seats: frozenset[int]
    confirmed_seats: set[int] = field(default_factory=set)

    @property
    def unconfirmed_seats(self) -> frozenset[int]:
        return self.required_seats - self.confirmed_seats

    def confirm(self, seat: int) -> bool:
        """
        Record a seat's confirmation; return whether every required seat has now confirmed.
        """
        if seat not in self.required_seats:
            logger.warning("seat is not in required_seats, ignoring", seat=seat)
            return False

        self.confirmed_seats.add(seat)
        return not self.unconfirmed_seats
