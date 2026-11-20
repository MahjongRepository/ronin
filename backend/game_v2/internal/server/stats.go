package server

import (
	"slices"
	"sync"
	"sync/atomic"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
)

var serverCloseCodes = [...]session.CloseCode{
	session.CloseGameEnded,
	session.CloseInvalidAction,
	session.CloseInternalError,
	session.CloseAuthTimeout,
	session.CloseReplaced,
	closeTooManyDecodes,
}

type socketStats struct {
	connections   atomic.Int64
	accepted      atomic.Int64
	messagesIn    atomic.Int64
	bytesIn       atomic.Int64
	messagesOut   atomic.Int64
	bytesOut      atomic.Int64
	handlingNanos atomic.Int64
	handled       atomic.Int64
	malformed     atomic.Int64
	rateLimited   atomic.Int64

	mu     sync.Mutex
	closes map[int]int64
}

func initialCloses() map[int]int64 {
	closes := make(map[int]int64, len(serverCloseCodes))
	for _, code := range serverCloseCodes {
		closes[int(code)] = 0
	}
	return closes
}

func (s *socketStats) countIn(n int) {
	s.messagesIn.Add(1)
	s.bytesIn.Add(int64(n))
}

func (s *socketStats) countOut(n int) {
	s.messagesOut.Add(1)
	s.bytesOut.Add(int64(n))
}

func (s *socketStats) countHandled(took time.Duration) {
	s.handled.Add(1)
	s.handlingNanos.Add(int64(took))
}

func (s *socketStats) countClose(code int) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.closes[code]++
}

type closeCount struct {
	code  int
	count int64
}

func (s *socketStats) closeCounts() []closeCount {
	s.mu.Lock()
	defer s.mu.Unlock()

	counts := make([]closeCount, 0, len(s.closes))
	for code, count := range s.closes {
		counts = append(counts, closeCount{code: code, count: count})
	}
	slices.SortFunc(counts, func(a, b closeCount) int { return a.code - b.code })
	return counts
}

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
