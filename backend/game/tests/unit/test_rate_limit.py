"""Tests for the token bucket rate limiter."""

from unittest.mock import patch

from game.server.rate_limit import TokenBucket


class TestTokenBucket:
    def test_burst_allows_up_to_capacity(self):
        """Burst capacity messages are allowed immediately."""
        bucket = TokenBucket(rate=1.0, burst=5)
        results = [bucket.consume() for _ in range(5)]
        assert all(results)

    def test_over_burst_rejected(self):
        """Messages beyond burst capacity are rejected without refill time."""
        bucket = TokenBucket(rate=1.0, burst=3)
        for _ in range(3):
            bucket.consume()
        assert bucket.consume() is False

    def test_refill_restores_tokens(self):
        """After time passes, tokens are refilled at the configured rate."""
        bucket = TokenBucket(rate=10.0, burst=5)
        # Drain all tokens
        for _ in range(5):
            bucket.consume()
        assert bucket.consume() is False

        # Advance time by 0.5s -> should refill 5 tokens (10/s * 0.5s)
        with patch("game.server.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = bucket._last_refill + 0.5
            assert bucket.consume() is True

    def test_refill_capped_at_burst(self):
        """Tokens never exceed burst capacity even after long idle periods."""
        bucket = TokenBucket(rate=10.0, burst=5)

        # Advance time by a large amount
        with patch("game.server.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = bucket._last_refill + 100.0
            # Should get at most burst (5) tokens
            results = [bucket.consume() for _ in range(5)]
            assert all(results)
            assert bucket.consume() is False

    def test_sustained_rate_enforcement(self):
        """At steady state, only rate-per-second messages are allowed."""
        bucket = TokenBucket(rate=2.0, burst=2)
        # Drain burst
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

        # After 0.5s at rate=2, we get 1 token
        with patch("game.server.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = bucket._last_refill + 0.5
            assert bucket.consume() is True
            assert bucket.consume() is False
