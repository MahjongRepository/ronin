package session

import (
	"slices"
	"sync"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// DefaultObserveDelay is the observer delay of a Config that sets none.
const DefaultObserveDelay = 5 * time.Minute

const observedRetention = time.Minute

// Observation is what an observer may see of a game: the game as the lobby lists it, how long
// until its first records may be seen, the records collected at least the delay ago from the
// cursor asked for, the cursor after them, and whether the game's end is itself that old and every
// record was returned. Records hold no seed and are never written to.
type Observation struct {
	Game        StartedGame
	AvailableIn time.Duration
	Records     []wire.Map
	Next        int
	Ended       bool
}

type observerTimeline struct {
	started StartedGame

	mu      sync.Mutex
	entries []stampedRecord
	endedAt play.Option[time.Time]
}

type stampedRecord struct {
	stamp  time.Time
	record wire.Map
}

type observerEntry struct {
	timeline  *observerTimeline
	expiresAt play.Option[time.Time]
}

func newObserverTimeline(started StartedGame) *observerTimeline {
	return &observerTimeline{started: started}
}

func (t *observerTimeline) follow(log *messaging.ReplayLog, stamp time.Time) {
	t.mu.Lock()
	defer t.mu.Unlock()

	for _, record := range log.RecordsSince(len(t.entries)) {
		t.entries = append(t.entries, stampedRecord{stamp: stamp, record: seedless(record)})
	}
}

func seedless(record wire.Map) wire.Map {
	if _, seeded := record.Get(wire.KeySeed); !seeded {
		return record
	}
	return slices.DeleteFunc(slices.Clone(record), func(f wire.Field) bool { return f.Key == wire.KeySeed })
}

func (t *observerTimeline) seal(endedAt time.Time) {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.endedAt = play.Some(endedAt)
}

func (t *observerTimeline) observe(from int, now time.Time, delay time.Duration) Observation {
	t.mu.Lock()
	defer t.mu.Unlock()

	cutoff := now.Add(-delay)
	next := from
	for next < len(t.entries) && !t.entries[next].stamp.After(cutoff) {
		next++
	}
	var records []wire.Map
	for _, entry := range t.entries[min(from, next):next] {
		records = append(records, entry.record)
	}
	return Observation{
		Game:        t.started,
		AvailableIn: max(0, t.started.StartedAt.Sub(cutoff)),
		Records:     records,
		Next:        next,
		Ended:       t.endedAt.OK && !t.endedAt.Value.After(cutoff) && next == len(t.entries),
	}
}

// Observe returns what an observer may see of a game from cursor from, a count of records, not
// below zero. It reports false for a game that never started playing, or whose end is past the
// delay and the retention after it.
func (m *Manager) Observe(gameID string, from int) (Observation, bool) {
	now := m.cfg.Clock.Now()
	t := m.observedTimeline(gameID, now)
	if t == nil {
		return Observation{}, false
	}
	return t.observe(from, now, m.cfg.ObserveDelay), true
}

func (m *Manager) observedTimeline(gameID string, now time.Time) *observerTimeline {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.sweepObservedLocked(now)
	if entry := m.observed[gameID]; entry != nil {
		return entry.timeline
	}
	return nil
}

func (m *Manager) sweepObservedLocked(now time.Time) {
	for id, entry := range m.observed {
		if entry.expiresAt.OK && !entry.expiresAt.Value.After(now) {
			delete(m.observed, id)
		}
	}
}
