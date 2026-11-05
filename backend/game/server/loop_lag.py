import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()

PROBE_INTERVAL_SECONDS = 1.0
LAG_WINDOW_SECONDS = 60.0


@dataclass
class LoopLagProbe:
    """
    Measure how late the event loop wakes a sleeper, keeping the observations of the last minute.

    The maximum is a rolling one by age and is never reset on read, since several readers poll `/status`.
    """

    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    _observations: deque[tuple[float, float]] = field(default_factory=deque)

    async def run(self) -> None:
        """
        Sleep and record each wake-up's lateness until cancelled; an unexpected error is logged and ends the probe.
        """
        try:
            while True:
                due = self.clock() + PROBE_INTERVAL_SECONDS
                await self.sleep(PROBE_INTERVAL_SECONDS)
                woke = self.clock()
                self._observations.append((woke, max(0.0, woke - due)))
                self._drop_expired()
        except Exception:
            logger.exception("event loop lag probe failed")
            self._observations.clear()

    @property
    def max_ms(self) -> float | None:
        """
        Return the worst lateness observed in the last minute in milliseconds, or None without an observation.
        """
        self._drop_expired()
        if not self._observations:
            return None

        return max(lateness for _, lateness in self._observations) * 1000

    def _drop_expired(self) -> None:
        cutoff = self.clock() - LAG_WINDOW_SECONDS
        while self._observations and self._observations[0][0] <= cutoff:
            self._observations.popleft()
