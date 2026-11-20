package session

import (
	"sync"
	"time"
)

const (
	lagWindowSeconds = 60
	millisPerSecond  = 1000
)

type lagWindow struct {
	mu      sync.Mutex
	buckets [lagWindowSeconds]lagBucket
}

type lagBucket struct {
	second int64
	worst  time.Duration
	seen   bool
}

func (w *lagWindow) observe(at time.Time, delay time.Duration) {
	w.mu.Lock()
	defer w.mu.Unlock()

	second := at.Unix()
	b := &w.buckets[second%lagWindowSeconds]
	if !b.seen || b.second != second {
		*b = lagBucket{second: second, seen: true}
	}
	b.worst = max(b.worst, delay)
}

func (w *lagWindow) worstMillis(at time.Time) (float64, bool) {
	w.mu.Lock()
	defer w.mu.Unlock()

	var worst time.Duration
	seen := false
	oldest := at.Unix() - lagWindowSeconds
	for _, b := range w.buckets {
		if b.seen && b.second > oldest {
			worst, seen = max(worst, b.worst), true
		}
	}
	return worst.Seconds() * millisPerSecond, seen
}
