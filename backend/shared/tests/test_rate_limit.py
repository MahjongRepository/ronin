from unittest.mock import patch

from shared.rate_limit import PRUNE_INTERVAL_SECONDS, KeyedRateLimiter, TokenBucket


class TestTokenBucket:
    def test_token_bucket__when_within_burst__should_allow_consumption(self):
        bucket = TokenBucket(rate=1.0, burst=5)
        results = [bucket.consume() for _ in range(5)]
        assert all(results)

    def test_token_bucket__when_burst_exhausted__should_reject(self):
        bucket = TokenBucket(rate=1.0, burst=3)
        for _ in range(3):
            bucket.consume()
        assert bucket.consume() is False

    def test_token_bucket__when_time_passes__should_refill_tokens(self):
        bucket = TokenBucket(rate=10.0, burst=5)
        # Drain all tokens
        for _ in range(5):
            bucket.consume()
        assert bucket.consume() is False

        # Advance time by 0.5s -> should refill 5 tokens (10/s * 0.5s)
        with patch("shared.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = bucket._last_refill + 0.5
            assert bucket.consume() is True

    def test_token_bucket__when_long_idle__should_cap_refill_at_burst(self):
        bucket = TokenBucket(rate=10.0, burst=5)

        # Advance time by a large amount
        with patch("shared.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = bucket._last_refill + 100.0
            # Should get at most burst (5) tokens
            results = [bucket.consume() for _ in range(5)]
            assert all(results)
            assert bucket.consume() is False

    def test_token_bucket__when_drained__should_allow_only_refilled_tokens(self):
        bucket = TokenBucket(rate=2.0, burst=2)
        # Drain burst
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

        # After 0.5s at rate=2, we get 1 token
        with patch("shared.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = bucket._last_refill + 0.5
            assert bucket.consume() is True
            assert bucket.consume() is False


class TestKeyedRateLimiter:
    def test_keyed_rate_limiter__when_one_key_is_exhausted__should_still_allow_another_key(self):
        limiter = KeyedRateLimiter(rate=1.0, burst=2)
        first_key = [limiter.consume("10.0.0.1") for _ in range(3)]

        assert first_key == [True, True, False]
        assert limiter.consume("10.0.0.2") is True

    def test_keyed_rate_limiter__when_a_prune_runs_before_an_exhausted_key_refills__should_keep_refusing_it(self):
        with patch("shared.rate_limit.time") as mock_time:
            mock_time.monotonic.return_value = 1000.0
            limiter = KeyedRateLimiter(rate=0.01, burst=1)
            assert limiter.consume("10.0.0.1") is True

            mock_time.monotonic.return_value = 1000.0 + PRUNE_INTERVAL_SECONDS
            assert limiter.consume("10.0.0.2") is True
            assert limiter.consume("10.0.0.1") is False
