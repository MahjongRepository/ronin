import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import structlog

from game.logic.enums import TimeoutType
from game.logic.timer import TimerConfig, TurnTimer
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from game.session.models import Game

logger = structlog.get_logger()


@dataclass(frozen=True)
class TimerFiring:
    """
    A timer that fired, with the arm generation it fired at.
    """

    timer: TurnTimer
    generation: int


TimeoutCallback = Callable[[str, TimeoutType, int, TimerFiring], Awaitable[None]]


class TimerManager:
    """
    Manage per-player turn timer lifecycle for all active games.

    This class handles timer creation, start, stop, and cleanup. It does NOT inspect event types -- the caller
    (SessionManager) extracts relevant information from events and calls the appropriate methods.

    A fired timer has already detached its task from its `TurnTimer`, so no cancel path cancels a running callback; the
    manager keeps those callbacks in `_running` until they finish, and `shutdown` awaits them. A stop, cancel or
    restart of that seat while the callback waits for the game lock supersedes it instead: `is_superseded` tells the
    callback to drop its default action.
    """

    def __init__(self, on_timeout: TimeoutCallback) -> None:
        self._timers: dict[str, dict[int, TurnTimer]] = {}
        self._on_timeout = on_timeout
        self._running: set[asyncio.Task[None]] = set()

    def create_timers(self, *, game_id: str, seats: list[int], config: TimerConfig | None = None) -> None:
        """
        Create TurnTimer instances for the given player seats.
        """
        self._timers[game_id] = {seat: TurnTimer(config=config) for seat in seats}

    def get_timer(self, game_id: str, seat: int) -> TurnTimer | None:
        """
        Get the timer for a specific seat in a game.
        """
        timers = self._timers.get(game_id)
        return timers.get(seat) if timers else None

    def add_timer(
        self,
        game_id: str,
        seat: int,
        config: TimerConfig | None = None,
        bank_seconds: float | None = None,
    ) -> None:
        """
        Create a timer for a single seat (used on reconnection).

        If bank_seconds is provided, the timer is initialized with that bank time instead of the default
        initial_bank_seconds (preserves bank across disconnect).
        """
        timers = self._timers.get(game_id)
        if timers is not None:
            timers[seat] = TurnTimer(config=config, bank_seconds=bank_seconds)

    def remove_timer(self, game_id: str, seat: int) -> TurnTimer | None:
        """
        Remove and return the timer for a seat (used on disconnect).
        """
        timers = self._timers.get(game_id)
        if timers is None:
            return None

        return timers.pop(seat, None)

    def cleanup_game(self, game_id: str) -> None:
        """
        Cancel all timers and remove timer storage for a game.
        """
        timers = self._timers.pop(game_id, None)
        if timers:
            for timer in timers.values():
                timer.cancel()

    def stop_player_timer(self, game_id: str, seat: int) -> None:
        """
        Stop a player's timer, deducting elapsed bank time.
        """
        timer = self.get_timer(game_id, seat)
        if timer:
            timer.stop()

    def cancel_other_timers(self, game_id: str, exclude_seat: int) -> None:
        """
        Cancel meld timers for all seats except the given one.
        """
        timers = self._timers.get(game_id)
        if timers:
            for seat, timer in timers.items():
                if seat != exclude_seat:
                    timer.cancel()

    def cancel_all(self, game_id: str) -> None:
        """
        Cancel all timers for a game without removing them.
        """
        timers = self._timers.get(game_id)
        if timers:
            for timer in timers.values():
                timer.cancel()

    def consume_bank(self, game_id: str, seat: int) -> None:
        """
        Deduct elapsed bank time without cancelling (for timeout callbacks).
        """
        timer = self.get_timer(game_id, seat)
        if timer:
            timer.consume_bank()

    def add_round_bonus(self, game_id: str) -> None:
        """
        Add round bonus time to all timers for a game.
        """
        timers = self._timers.get(game_id)
        if timers:
            for timer in timers.values():
                timer.add_round_bonus()

    def start_turn_timer(self, game_id: str, seat: int) -> None:
        """
        Start a turn timer for the given seat.
        """
        timer = self.get_timer(game_id, seat)
        if timer is not None:
            timer.start_turn_timer(lambda gid=game_id, s=seat, t=timer: self._run_callback(gid, TimeoutType.TURN, s, t))

    def start_meld_timer(self, game_id: str, seat: int) -> None:
        """
        Start a meld timer for the given seat.
        """
        timer = self.get_timer(game_id, seat)
        if timer is not None:
            timer.start_meld_timer(lambda gid=game_id, s=seat, t=timer: self._run_callback(gid, TimeoutType.MELD, s, t))

    def start_round_advance_timers(self, game: Game) -> None:
        """
        Start fixed-duration timers for players to confirm round advancement.
        """
        game_id = game.game_id
        timers = self._timers.get(game_id)
        if timers is None:
            return

        timeout = game.settings.round_advance_timeout_seconds
        for player in list(game.players.values()):
            if player.seat is not None:
                timer = timers.get(player.seat)
                if timer is not None:
                    timer.start_fixed_timer(
                        timeout,
                        lambda gid=game_id, s=player.seat, t=timer: self._run_callback(
                            gid,
                            TimeoutType.ROUND_ADVANCE,
                            s,
                            t,
                        ),
                    )

    def is_superseded(self, game_id: str, seat: int, firing: TimerFiring) -> bool:
        """
        Check whether the seat's timer was replaced, stopped, cancelled or re-armed since it fired.
        """
        return self.get_timer(game_id, seat) is not firing.timer or firing.timer.generation != firing.generation

    async def _run_callback(self, game_id: str, timeout_type: TimeoutType, seat: int, timer: TurnTimer) -> None:
        """
        Run the timeout callback inside the fired timer's task, tracked until it finishes.
        """
        firing = TimerFiring(timer=timer, generation=timer.generation)
        task = cast("asyncio.Task[None]", asyncio.current_task())
        self._running.add(task)
        try:
            await self._on_timeout(game_id, timeout_type, seat, firing)
        finally:
            self._running.discard(task)

    async def shutdown(self) -> None:
        """
        Cancel every sleeping timer and wait for the callbacks already running.
        """
        sleeping = [timer.task for timers in self._timers.values() for timer in timers.values()]
        self._timers.clear()
        await cancel_and_wait([task for task in sleeping if task is not None], finalizing=list(self._running))
