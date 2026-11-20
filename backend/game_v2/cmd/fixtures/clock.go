package main

import (
	"slices"
	"sync"
	"time"
)

type virtualClock struct {
	mu     sync.Mutex
	now    time.Duration
	armed  uint64
	timers []*virtualTimer
}

type virtualTimer struct {
	at    time.Duration
	order uint64
	fire  func()
	done  bool
}

func clockEpoch() time.Time {
	return time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC)
}

// Now returns the virtual time: the epoch plus how far the harness moved the clock.
func (c *virtualClock) Now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()

	return clockEpoch().Add(c.now)
}

// AfterFunc keeps f to run once the harness moves the clock to d from now; the harness runs it on
// its own goroutine.
func (c *virtualClock) AfterFunc(d time.Duration, f func()) func() bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.armed++
	t := &virtualTimer{at: c.now + d, order: c.armed, fire: f}
	c.timers = append(c.timers, t)
	return func() bool {
		c.mu.Lock()
		defer c.mu.Unlock()

		stopped := !t.done
		t.done = true
		return stopped
	}
}

func (c *virtualClock) elapsed() time.Duration {
	c.mu.Lock()
	defer c.mu.Unlock()

	return c.now
}

func (c *virtualClock) armedAt(at time.Duration) bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	return at > c.now && slices.ContainsFunc(c.timers, func(t *virtualTimer) bool { return !t.done && t.at == at })
}

func (c *virtualClock) takeDue(until time.Duration) (func(), bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.timers = slices.DeleteFunc(c.timers, func(t *virtualTimer) bool { return t.done })
	var next *virtualTimer
	for _, t := range c.timers {
		if t.at <= until && (next == nil || t.at < next.at || t.at == next.at && t.order < next.order) {
			next = t
		}
	}
	if next == nil {
		return nil, false
	}

	next.done = true
	c.now = max(c.now, next.at)
	return next.fire, true
}

func (c *virtualClock) advanceTo(at time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.now = at
}
