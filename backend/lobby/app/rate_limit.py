import time

PRUNE_INTERVAL_SECONDS = 60.0


class TokenBucket:
    """
    Rate limiter using the token bucket algorithm.

    Tokens are added at a constant rate up to a maximum burst capacity. Each consume() call removes one token; returns
    False when the bucket is empty (caller should throttle).
    """

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        """
        Try to consume one token.

        Returns True if allowed, False if rate-limited.
        """
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True

        return False

    def is_refilled(self) -> bool:
        """
        Whether the bucket is back at its full burst, so dropping it loses nothing.
        """
        return self._tokens + (time.monotonic() - self._last_refill) * self._rate >= self._burst


class KeyedRateLimiter:
    """
    One ``TokenBucket`` per key, such as a client IP.

    The first ``consume`` after each ``PRUNE_INTERVAL_SECONDS`` drops every refilled bucket in one pass, so the map
    holds only keys used within about ``burst / rate`` seconds, and a depleted key keeps its quota.
    """

    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: dict[str, TokenBucket] = {}
        self._next_prune = time.monotonic() + PRUNE_INTERVAL_SECONDS

    def consume(self, key: str) -> bool:
        """
        Try to consume one token from ``key``'s bucket; False when ``key`` is rate-limited.
        """
        now = time.monotonic()
        if now >= self._next_prune:
            self._buckets = {k: b for k, b in self._buckets.items() if not b.is_refilled()}
            self._next_prune = now + PRUNE_INTERVAL_SECONDS

        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = TokenBucket(rate=self._rate, burst=self._burst)

        return bucket.consume()
