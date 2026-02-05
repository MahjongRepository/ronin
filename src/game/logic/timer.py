"""
Server-side turn timer with bank time management.

Uses a bank system for turn time (initial + round bonus) and a fixed timer for meld decisions.
On timeout, callbacks trigger auto-actions (tsumogiri for turns, pass for melds).
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class TimerConfig(BaseModel):
    """Configuration for player turn timers."""

    # TODO: increase these limits for longer games or different game modes
    initial_bank_seconds: float = 3
    round_bonus_seconds: float = 2
    meld_decision_seconds: float = 2


class TurnTimer:
    """
    Manage action timers for a human player in a game.

    Uses a bank system for turn time (initial + round bonus) and a fixed timer for meld decisions.
    """

    def __init__(self, config: TimerConfig | None = None) -> None:
        self._config = config or TimerConfig()
        self._bank_seconds: float = self._config.initial_bank_seconds
        self._active_task: asyncio.Task[None] | None = None
        self._turn_start_time: float | None = None

    @property
    def remaining_bank(self) -> float:
        """Return remaining bank time, accounting for any active turn timer."""
        if self._turn_start_time is not None:
            elapsed = time.monotonic() - self._turn_start_time
            return max(0, self._bank_seconds - elapsed)
        return self._bank_seconds

    def add_round_bonus(self) -> None:
        """Add round bonus time to the bank."""
        self._bank_seconds += self._config.round_bonus_seconds

    def start_turn_timer(self, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """Start the turn timer using bank time."""
        self.cancel()
        self._turn_start_time = time.monotonic()
        self._active_task = asyncio.create_task(self._run_timer(self.remaining_bank, on_timeout))

    def start_meld_timer(self, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """Start a fixed meld decision timer (does not consume bank time)."""
        self.start_fixed_timer(self._config.meld_decision_seconds, on_timeout)

    def start_fixed_timer(self, duration: float, on_timeout: Callable[[], Awaitable[None]]) -> None:
        """Start a timer with a fixed duration (not using bank time)."""
        self.cancel()
        self._turn_start_time = None  # don't consume bank time
        self._active_task = asyncio.create_task(self._run_timer(duration, on_timeout))

    def stop(self) -> None:
        """Stop the active timer and deduct elapsed time from bank."""
        self.cancel()
        self._deduct_bank_time()

    def consume_bank(self) -> None:
        """
        Deduct elapsed bank time without cancelling the task.

        Used by timeout callbacks that execute within the timer task itself,
        where cancelling the task would abort the callback.
        """
        self._deduct_bank_time()

    def cancel(self) -> None:
        """Cancel the active timer without deducting bank time."""
        if self._active_task is not None and not self._active_task.done():
            self._active_task.cancel()
        self._active_task = None

    def _deduct_bank_time(self) -> None:
        if self._turn_start_time is not None:
            elapsed = time.monotonic() - self._turn_start_time
            self._bank_seconds = max(0, self._bank_seconds - elapsed)
            self._turn_start_time = None

    async def _run_timer(self, seconds: float, on_timeout: Callable[[], Awaitable[None]]) -> None:
        try:
            await asyncio.sleep(seconds)
            await on_timeout()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("timer callback failed")
