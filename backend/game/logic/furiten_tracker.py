"""Track per-player furiten state changes across game rounds."""

from typing import TYPE_CHECKING

from game.logic.enums import RoundPhase
from game.logic.events import EventType, FuritenEvent, SeatTarget, ServiceEvent
from game.logic.settings import NUM_PLAYERS
from game.logic.win import is_effective_furiten

if TYPE_CHECKING:
    from game.logic.state import MahjongRoundState


class FuritenTracker:
    """Track per-seat furiten state and emit change events.

    Maintain a boolean per seat per game. After each action, the caller
    passes the current round state and the tracker compares effective furiten
    against the last known value, emitting FuritenEvent for any changes.

    Skip recomputation for players whose object identity hasn't changed
    since the last check. Pydantic model_copy preserves object identity
    for unchanged players, so same id() means same tiles, discards, and
    furiten flags — the result is guaranteed identical.

    Follow the same pattern as RoundAdvanceManager: pure state tracking,
    no side effects, narrow API, cleanup_game() for teardown.
    """

    def __init__(self) -> None:
        self._state: dict[str, dict[int, bool]] = {}
        self._player_ids: dict[str, dict[int, int]] = {}

    def init_game(self, game_id: str) -> None:
        """Initialize furiten tracking for a new game or round."""
        self._state[game_id] = dict.fromkeys(range(NUM_PLAYERS), False)
        self._player_ids[game_id] = {}

    def check_changes(
        self,
        game_id: str,
        round_state: MahjongRoundState,
    ) -> list[ServiceEvent]:
        """Check all seats for furiten state changes and return events.

        Only check when the round is in PLAYING phase. Skip seats where
        the player object is unchanged (same id()) since the last call.
        """
        if round_state.phase != RoundPhase.PLAYING:
            return []

        if game_id not in self._state:
            return []

        furiten_state = self._state[game_id]
        player_ids = self._player_ids[game_id]
        events: list[ServiceEvent] = []

        for seat in range(NUM_PLAYERS):
            player = round_state.players[seat]
            pid = id(player)

            if pid == player_ids.get(seat):
                continue

            player_ids[seat] = pid
            current = is_effective_furiten(player)
            previous = furiten_state.get(seat, False)

            if current != previous:
                furiten_state[seat] = current
                events.append(
                    ServiceEvent.model_construct(
                        event=EventType.FURITEN,
                        data=FuritenEvent(
                            is_furiten=current,
                            target=f"seat_{seat}",
                        ),
                        target=SeatTarget(seat=seat),
                    ),
                )

        return events

    def cleanup_game(self, game_id: str) -> None:
        """Remove furiten state for a game."""
        self._state.pop(game_id, None)
        self._player_ids.pop(game_id, None)
