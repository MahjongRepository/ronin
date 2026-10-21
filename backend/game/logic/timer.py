from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from game.logic.settings import GameSettings


class TimerConfig(BaseModel):
    """
    Configuration for player turn timers.
    """

    base_turn_seconds: float = 5
    initial_bank_seconds: float = 20
    max_bank_seconds: float = 60
    round_bonus_seconds: float = 10
    meld_decision_seconds: float = 5

    @classmethod
    def from_settings(cls, settings: GameSettings) -> TimerConfig:
        """
        Build TimerConfig from GameSettings.
        """
        return cls(
            base_turn_seconds=settings.base_turn_seconds,
            initial_bank_seconds=settings.initial_bank_seconds,
            max_bank_seconds=settings.max_bank_seconds,
            round_bonus_seconds=settings.round_bonus_seconds,
            meld_decision_seconds=settings.meld_decision_seconds,
        )


class TurnTimer:
    """
    Manage action timers for a player in a game.

    Uses a two-phase timer: base time (free, resets each turn) followed by bank time
    (drains only when base time expires). Meld decisions use a separate fixed timer.
    """

    def __init__(self, config: TimerConfig | None = None, bank_seconds: float | None = None) -> None:
        self._config = config or TimerConfig()
        self._bank_seconds: float = bank_seconds if bank_seconds is not None else self._config.initial_bank_seconds
        self._active_task: asyncio.Task[None] | None = None
        self._turn_start_time: float | None = None
        self._generation = 0

    @property
    def task(self) -> asyncio.Task[None] | None:
        """
        The sleeping timer task, or None once it fired or was cancelled.
        """
        return self._active_task

    @property
    def generation(self) -> int:
        """
        Arm count, bumped by every start, stop and cancel: a fired callback whose captured value no longer matches was
        superseded while it waited.
        """
        return self._generation

    @property
    def bank_seconds(self) -> float:
        """
        Remaining bank time (seconds).
        """
        return self._bank_seconds

    def add_round_bonus(self) -> None:
        """
        Add round bonus time to the bank, capped at max_bank_seconds.
        """
        self._bank_seconds = min(
            self._bank_seconds + self._config.round_bonus_seconds,
            self._config.max_bank_seconds,
        )

    def start_turn_timer(self, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """
        Start the turn timer using base time + bank time.
        """
        self.cancel()
        self._turn_start_time = time.monotonic()
        total = self._config.base_turn_seconds + self._bank_seconds
        self._active_task = asyncio.create_task(self._run_timer(total, on_timeout))

    def start_meld_timer(self, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """
        Start a fixed meld decision timer (does not consume bank time).
        """
        self.start_fixed_timer(self._config.meld_decision_seconds, on_timeout)

    def start_fixed_timer(self, duration: float, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """
        Start a timer with a fixed duration (not using bank time).
        """
        self.cancel()
        self._turn_start_time = None  # don't consume bank time
        self._active_task = asyncio.create_task(self._run_timer(duration, on_timeout))

    def stop(self) -> None:
        """
        Stop the active timer and deduct elapsed time from bank.
        """
        self.cancel()
        self._deduct_bank_time()

    def consume_bank(self) -> None:
        """
        Deduct elapsed bank time without touching the task (for the timeout callback of this timer).
        """
        self._deduct_bank_time()

    def cancel(self) -> None:
        """
        Cancel the active timer without deducting bank time.
        """
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()

        self._active_task = None
        self._generation += 1

    def _deduct_bank_time(self) -> None:
        if self._turn_start_time is not None:
            elapsed = time.monotonic() - self._turn_start_time
            bank_used = max(0, elapsed - self._config.base_turn_seconds)
            self._bank_seconds = max(0, self._bank_seconds - bank_used)
            self._turn_start_time = None

    async def _run_timer(self, seconds: float, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """
        Sleep, then detach this task from the timer and run the callback.

        Detaching first keeps the callback safe from its own timer: a cancel, stop or restart of this seat inside the
        callback finds no active task, and a timer the callback arms stays armed. Such a cancel still bumps
        `generation`, which is how a callback still waiting to act learns it was superseded. The callback owns its
        errors.
        """
        await asyncio.sleep(seconds)
        self._active_task = None
        await on_timeout()
