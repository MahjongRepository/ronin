from typing import TYPE_CHECKING

from game.logic.enums import RoundPhase
from game.logic.events import FuritenEvent, SeatTarget
from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import DRAWN_HAND_REMAINDER
from game.logic.win import is_effective_furiten

if TYPE_CHECKING:
    from game.logic.state import MahjongPlayer, MahjongRoundState


class FuritenTracker:
    """
    Track one round's per-seat furiten state and emit change events.

    Hold a boolean per seat, all False at the round's start (a new round gets a new tracker). After each action, the
    caller passes the current round state and the tracker compares effective furiten against the last known value,
    emitting FuritenEvent for any changes. The held value is what the seat was last told, so the reconnect snapshot
    reads it too.

    Discard furiten is a property of a waiting hand. A seat holding a drawn hand (3n+2 tiles: after its draw, or its own
    pon or chi) has no waits, so it keeps the value it carried into the turn until its discard; a temporary or riichi
    furiten flag set on the way in (a ron passed or missed on the discard it then drew or called after) still turns it
    on.

    Skip recomputation for a seat whose player object is the one checked last time. Pydantic model_copy preserves object
    identity for unchanged players, and the tracker holds the checked object, so an identical object means identical
    tiles, discards and furiten flags.
    """

    def __init__(self) -> None:
        self._state: dict[int, bool] = dict.fromkeys(range(NUM_PLAYERS), False)
        self._checked_players: dict[int, MahjongPlayer] = {}

    def is_furiten(self, seat: int) -> bool:
        """
        Return the furiten last reported to the seat.
        """
        return self._state[seat]

    def check_changes(self, round_state: MahjongRoundState) -> list[FuritenEvent]:
        """
        Check all seats for furiten state changes and return events.

        Only check when the round is in PLAYING phase. Skip seats whose player object is the one checked by the last
        call.
        """
        if round_state.phase != RoundPhase.PLAYING:
            return []

        events: list[FuritenEvent] = []
        for seat in range(NUM_PLAYERS):
            player = round_state.players[seat]
            if player is self._checked_players.get(seat):
                continue

            self._checked_players[seat] = player
            current = self._current_furiten(seat, player)
            if current != self._state[seat]:
                self._state[seat] = current
                events.append(FuritenEvent(is_furiten=current, target=SeatTarget(seat=seat)))

        return events

    def _current_furiten(self, seat: int, player: MahjongPlayer) -> bool:
        """
        Return the seat's effective furiten, or for a drawn hand the value carried into the turn or a flag set since.
        """
        if len(player.tiles) % 3 != DRAWN_HAND_REMAINDER:
            return is_effective_furiten(player)

        return self._state[seat] or player.is_temporary_furiten or player.is_riichi_furiten
