from typing import TYPE_CHECKING

from game.logic.enums import RoundPhase
from game.logic.events import FuritenEvent, SeatTarget, ServiceEvent
from game.logic.settings import NUM_PLAYERS
from game.logic.win import is_effective_furiten

if TYPE_CHECKING:
    from game.logic.state import MahjongPlayer, MahjongRoundState


class FuritenTracker:
    """
    Track one round's per-seat furiten state and emit change events.

    Hold a boolean per seat, all False at the round's start (a new round gets a new tracker). After each action, the
    caller passes the current round state and the tracker compares effective furiten against the last known value,
    emitting FuritenEvent for any changes.

    Skip recomputation for a seat whose player object is the one checked last time. Pydantic model_copy preserves object
    identity for unchanged players, and the tracker holds the checked object, so an identical object means identical
    tiles, discards and furiten flags.
    """

    def __init__(self) -> None:
        self._state: dict[int, bool] = dict.fromkeys(range(NUM_PLAYERS), False)
        self._checked_players: dict[int, MahjongPlayer] = {}

    def check_changes(self, round_state: MahjongRoundState) -> list[ServiceEvent]:
        """
        Check all seats for furiten state changes and return events.

        Only check when the round is in PLAYING phase. Skip seats whose player object is the one checked by the last
        call.
        """
        if round_state.phase != RoundPhase.PLAYING:
            return []

        events: list[ServiceEvent] = []
        for seat in range(NUM_PLAYERS):
            player = round_state.players[seat]
            if player is self._checked_players.get(seat):
                continue

            self._checked_players[seat] = player
            current = is_effective_furiten(player)
            if current != self._state[seat]:
                self._state[seat] = current
                events.append(
                    ServiceEvent.model_construct(data=FuritenEvent(is_furiten=current, target=SeatTarget(seat=seat))),
                )

        return events
