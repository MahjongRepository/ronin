import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from game.logic.enums import TimeoutType
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from game.session.models import Participant
    from game.session.timer import TurnTimer


@dataclass(frozen=True)
class TimerFiring:
    """
    A timer that fired, with the arm generation it fired at.
    """

    timer: TurnTimer
    generation: int

    @property
    def is_superseded(self) -> bool:
        """
        Whether the timer was stopped, cancelled or re-armed since it fired.
        """
        return self.timer.generation != self.generation


TimeoutCallback = Callable[["Participant", TimeoutType, TimerFiring], Awaitable[None]]


class TimerManager:
    """
    Arm participants' timers and track the timeout callbacks that are running.

    Each participant owns its `TurnTimer` for the whole game; this class only arms it with the session's callback. A
    fired timer has already detached its task from its `TurnTimer`, so no cancel path cancels a running callback; the
    manager keeps those callbacks in `_running` until they finish, and `shutdown` awaits them. A stop, cancel or restart
    of that timer while the callback waits for the game lock supersedes it instead (`TimerFiring.is_superseded`).
    """

    def __init__(self, on_timeout: TimeoutCallback) -> None:
        self._on_timeout = on_timeout
        self._running: set[asyncio.Task[None]] = set()

    def start_turn_timer(self, participant: Participant) -> None:
        timer = participant.timer
        timer.start_turn_timer(lambda: self._run_callback(participant, TimeoutType.TURN, timer))

    def start_meld_timer(self, participant: Participant) -> None:
        timer = participant.timer
        timer.start_meld_timer(lambda: self._run_callback(participant, TimeoutType.MELD, timer))

    def start_round_advance_timer(self, participant: Participant) -> None:
        timer = participant.timer
        timer.start_fixed_timer(
            participant.game.timer_config.round_advance_timeout_seconds,
            lambda: self._run_callback(participant, TimeoutType.ROUND_ADVANCE, timer),
        )

    async def _run_callback(self, participant: Participant, timeout_type: TimeoutType, timer: TurnTimer) -> None:
        """
        Run the timeout callback inside the fired timer's task, tracked until it finishes.
        """
        firing = TimerFiring(timer=timer, generation=timer.generation)
        task = cast("asyncio.Task[None]", asyncio.current_task())
        self._running.add(task)
        try:
            await self._on_timeout(participant, timeout_type, firing)
        finally:
            self._running.discard(task)

    async def shutdown(self, timers: list[TurnTimer]) -> None:
        """
        Cancel the given timers' sleeping tasks and wait for the callbacks already running.
        """
        sleeping = [timer.task for timer in timers if timer.task is not None]
        await cancel_and_wait(sleeping, finalizing=list(self._running))
