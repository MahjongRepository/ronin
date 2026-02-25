"""Token bucket rate limiter for WebSocket message throttling."""

import time


class TokenBucket:
    """Rate limiter using the token bucket algorithm.

    Tokens are added at a constant rate up to a maximum burst capacity.
    Each consume() call removes one token; returns False when the bucket
    is empty (caller should throttle).
    """

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate-limited."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
