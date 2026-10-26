from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable


class TimerConfig(BaseModel):
    """
    Pacing of a game: turn base and bank time, fixed meld, round-advance and pending-game timeouts, and the game start
    pause before the first deal (seconds).
    """

    base_turn_seconds: float = Field(default=5, ge=0)
    initial_bank_seconds: float = Field(default=20, gt=0)
    max_bank_seconds: float = 60
    round_bonus_seconds: float = Field(default=10, ge=0)
    meld_decision_seconds: float = Field(default=5, gt=0)
    round_advance_timeout_seconds: float = Field(default=15, gt=0)
    pending_game_timeout_seconds: float = Field(default=30, gt=0)
    game_start_pause_seconds: float = Field(default=3, ge=0)

    @model_validator(mode="after")
    def _validate_bank_cap(self) -> TimerConfig:
        if self.max_bank_seconds < self.initial_bank_seconds:
            raise ValueError("max_bank_seconds must be >= initial_bank_seconds")

        return self


class TurnTimer:
    """
    Manage action timers for a player in a game.

    Uses a two-phase timer: base time (free, resets each turn) followed by bank time
    (drains only when base time expires). Meld decisions use a separate fixed timer.
    """

    def __init__(self, config: TimerConfig) -> None:
        self._config = config
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

        return time.monotonic() - self._started_at

    def add_round_bonus(self) -> None:
        """
        Add round bonus time to the bank, capped at max_bank_seconds.
        """
        self._bank_seconds = min(
            self._bank_seconds + self._config.round_bonus_seconds,
            self._config.max_bank_seconds,
        )

    def start_turn_timer(self, on_timeout: Callable[[], None]) -> None:
        """
        Start the turn timer using base time + bank time.
        """
        self.cancel()
        self._turn_start_time = self._started_at = time.monotonic()
        total = self._config.base_turn_seconds + self._bank_seconds
        self._active_task = asyncio.create_task(self._run_timer(total, on_timeout))

    def start_meld_timer(self, on_timeout: Callable[[], None]) -> None:
        """
        Start a fixed meld decision timer (does not consume bank time).
        """
        self.start_fixed_timer(self._config.meld_decision_seconds, on_timeout)

    def start_fixed_timer(self, duration: float, on_timeout: Callable[[], None]) -> None:
        """
        Start a timer with a fixed duration (not using bank time).
        """
        self.cancel()
        self._turn_start_time = None  # don't consume bank time
        self._started_at = time.monotonic()
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
            elapsed = time.monotonic() - self._turn_start_time
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
