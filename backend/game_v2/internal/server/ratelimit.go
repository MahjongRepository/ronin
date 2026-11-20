package server

import "time"

// tokenBucket refills at rate tokens a second up to burst, and each take spends one. Only the
// goroutine reading its socket uses it.
type tokenBucket struct {
	rate   float64
	burst  float64
	tokens float64
	last   time.Time
}

func newTokenBucket(rate float64, burst int, now time.Time) tokenBucket {
	return tokenBucket{rate: rate, burst: float64(burst), tokens: float64(burst), last: now}
}

func (b *tokenBucket) take(now time.Time) bool {
	elapsed := now.Sub(b.last).Seconds()
	b.tokens = min(b.burst, b.tokens+elapsed*b.rate)
	b.last = now

	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}
