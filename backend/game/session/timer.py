from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Callable

    from game.logic.service import Awaiting


class TimerConfig(BaseModel):
    """
    Pace turns and calls with a shared per-hand bank, plus fixed round-advance and pending-game timeouts, the game start
    confirmation's timeout between the first deal and the dealer's first draw (zero skips the confirmation: the dealer
    draws at once), and the delay ahead of each AI player's turn action, so a human can follow AI turns one by one
    (seconds; a zero delay plays them at once).
    """

    base_turn_seconds: float = Field(default=10, ge=0)
    initial_bank_seconds: float = Field(default=20, gt=0)
    round_advance_timeout_seconds: float = Field(default=15, gt=0)
    pending_game_timeout_seconds: float = Field(default=30, gt=0)
    game_start_confirm_seconds: float = Field(default=10, ge=0)
    ai_turn_delay_seconds: float = Field(default=1, ge=0)

    def round_advance_seconds(self, awaiting: Awaiting) -> float:
        """
        How long a round advance waits: its timeout once for each result the round end shows in turn, or the game start
        confirmation's timeout for the one that starts the game.
        """
        if awaiting.starts_game:
            return self.game_start_confirm_seconds

        return self.round_advance_timeout_seconds * awaiting.results_shown


class TurnTimer:
    """
    Manage action timers for a player in a game.

    Uses a two-phase timer: base time (free, resets each turn) followed by bank time
    (drains only when base time expires). Turns and calls share the bank, reset each hand. The clock (monotonic seconds)
    times the bank and the elapsed time, and must agree with the event loop's clock, which times the sleeps: a harness
    that runs the loop on virtual time passes the loop's.
    """

    def __init__(self, config: TimerConfig, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._config = config
        self._clock = clock
        self._bank_seconds: float = config.initial_bank_seconds
        self._active_task: asyncio.Task[None] | None = None
        self._turn_start_time: float | None = None
        self._started_at: float | None = None

    @property
    def task(self) -> asyncio.Task[None] | None:
        """
        The sleeping timer task, or None once it fired or was cancelled.
        """
        return self._active_task

    @property
    def bank_seconds(self) -> float:
        """
        The bank left, as of the last stop: a running turn has not deducted from it yet.
        """
        return self._bank_seconds

    @property
    def elapsed_seconds(self) -> float | None:
        """
        How long the running timer has run, or None when no timer runs.
        """
        if self._active_task is None or self._started_at is None:
            return None

        return self._clock() - self._started_at

    def reset_bank(self) -> None:
        """
        Restore the hand's full bank.
        """
        self._bank_seconds = self._config.initial_bank_seconds

    def start_decision_timer(self, on_timeout: Callable[[], None]) -> None:
        """
        Start a turn or call timer using base time + bank time.
        """
        self.cancel()
        self._turn_start_time = self._started_at = self._clock()
        total = self._config.base_turn_seconds + self._bank_seconds
        self._active_task = asyncio.create_task(self._run_timer(total, on_timeout))

    def start_fixed_timer(self, duration: float, on_timeout: Callable[[], None]) -> None:
        """
        Start a timer with a fixed duration (not using bank time).
        """
        self.cancel()
        self._turn_start_time = None  # don't consume bank time
        self._started_at = self._clock()
        self._active_task = asyncio.create_task(self._run_timer(duration, on_timeout))

    def stop(self) -> None:
        """
        Stop the active timer and deduct elapsed time from bank.
        """
        self.cancel()
        self._deduct_bank_time()

    def cancel(self) -> None:
        """
        Cancel the active timer without deducting bank time.
        """
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()

        self._active_task = None

    def _deduct_bank_time(self) -> None:
        if self._turn_start_time is not None:
            elapsed = self._clock() - self._turn_start_time
            bank_used = max(0, elapsed - self._config.base_turn_seconds)
            self._bank_seconds = max(0, self._bank_seconds - bank_used)
            self._turn_start_time = None

    async def _run_timer(self, seconds: float, on_timeout: Callable[[], None]) -> None:
        """
        Sleep, then detach this task from the timer and run the callback.

        Detaching first keeps the callback safe from its own timer: a cancel, stop or restart of this seat inside the
        callback finds no active task, and a timer the callback arms stays armed. The callback is synchronous, so
        nothing can supersede it once it runs; a cancel after the sleep ended but before this task resumed still stops
        it here. The callback owns its errors.
        """
        await asyncio.sleep(seconds)
        self._active_task = None
        on_timeout()
