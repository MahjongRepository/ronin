"""Manage per-player turn timers for active games."""

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from game.logic.enums import TimeoutType
from game.logic.timer import TurnTimer

if TYPE_CHECKING:
    from game.session.models import Game

ROUND_ADVANCE_TIMEOUT = 15  # seconds to confirm round advancement

logger = logging.getLogger(__name__)

# Callback type: (game_id, timeout_type, seat) -> Awaitable[None]
TimeoutCallback = Callable[[str, TimeoutType, int], Awaitable[None]]


class TimerManager:
    """Manage per-player turn timer lifecycle for all active games.

    This class handles timer creation, start, stop, and cleanup. It does NOT
    inspect event types -- the caller (SessionManager) extracts relevant
    information from events and calls the appropriate methods.
    """

    def __init__(self, on_timeout: TimeoutCallback) -> None:
        self._timers: dict[str, dict[int, TurnTimer]] = {}
        self._on_timeout = on_timeout

    def create_timers(self, game_id: str, seats: list[int]) -> None:
        """Create TurnTimer instances for the given human seats."""
        self._timers[game_id] = {seat: TurnTimer() for seat in seats}

    def has_game(self, game_id: str) -> bool:
        """Check if timers exist for a game."""
        return game_id in self._timers

    def get_timer(self, game_id: str, seat: int) -> TurnTimer | None:
        """Get the timer for a specific seat in a game."""
        timers = self._timers.get(game_id)
        return timers.get(seat) if timers else None

    def remove_timer(self, game_id: str, seat: int) -> TurnTimer | None:
        """Remove and return the timer for a seat (used on disconnect)."""
        timers = self._timers.get(game_id)
        if timers is None:
            return None
        return timers.pop(seat, None)

    def cleanup_game(self, game_id: str) -> None:
        """Cancel all timers and remove timer storage for a game."""
        timers = self._timers.pop(game_id, None)
        if timers:
            for timer in timers.values():
                timer.cancel()

    def stop_player_timer(self, game_id: str, seat: int) -> None:
        """Stop a player's timer, deducting elapsed bank time."""
        timer = self.get_timer(game_id, seat)
        if timer:
            timer.stop()

    def cancel_other_timers(self, game_id: str, exclude_seat: int) -> None:
        """Cancel meld timers for all seats except the given one."""
        timers = self._timers.get(game_id)
        if timers:
            for seat, timer in timers.items():
                if seat != exclude_seat:
                    timer.cancel()

    def cancel_all(self, game_id: str) -> None:
        """Cancel all timers for a game without removing them."""
        timers = self._timers.get(game_id)
        if timers:
            for timer in timers.values():
                timer.cancel()

    def consume_bank(self, game_id: str, seat: int) -> None:
        """Deduct elapsed bank time without cancelling (for timeout callbacks)."""
        timer = self.get_timer(game_id, seat)
        if timer:
            timer.consume_bank()

    def add_round_bonus(self, game_id: str) -> None:
        """Add round bonus time to all timers for a game."""
        timers = self._timers.get(game_id)
        if timers:
            for timer in timers.values():
                timer.add_round_bonus()

    def start_turn_timer(self, game_id: str, seat: int) -> None:
        """Start a turn timer for the given seat."""
        timer = self.get_timer(game_id, seat)
        if timer is not None:
            timer.start_turn_timer(lambda gid=game_id, s=seat: self._on_timeout(gid, TimeoutType.TURN, s))

    def start_meld_timer(self, game_id: str, seat: int) -> None:
        """Start a meld timer for the given seat."""
        timer = self.get_timer(game_id, seat)
        if timer is not None:
            timer.start_meld_timer(lambda gid=game_id, s=seat: self._on_timeout(gid, TimeoutType.MELD, s))

    def start_round_advance_timers(self, game: Game) -> None:
        """Start fixed-duration timers for human players to confirm round advancement."""
        game_id = game.game_id
        timers = self._timers.get(game_id)
        if timers is None:
            return
        for player in game.players.values():
            if player.seat is not None:
                timer = timers.get(player.seat)
                if timer is not None:
                    timer.start_fixed_timer(
                        ROUND_ADVANCE_TIMEOUT,
                        lambda gid=game_id, s=player.seat: self._on_timeout(
                            gid, TimeoutType.ROUND_ADVANCE, s
                        ),
                    )
