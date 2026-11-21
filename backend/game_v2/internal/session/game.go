package session

import (
	"fmt"
	"iter"
	"log/slog"
	"runtime/debug"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	logAuthTimeout         = "auth timeout, closing unauthenticated connection"
	logTurnTimeout         = "turn timeout, auto-discarding"
	logMeldTimeout         = "meld timeout, auto-passing"
	logStaleAction         = "stale game action"
	logInvalidAction       = "invalid game action"
	logCalledTileMismatch  = "invalid call: tile_id mismatch"
	logPlayerReconnected   = "player reconnected"
	logConnectionTakenOver = "connection taken over"
	logSessionErrorSent    = "session error sent to client"
	logGameFailed          = "game failed"
	logAgentFallback       = "AI agent answer unusable, playing the default"
)

type lifecycle uint8

const (
	lifecyclePending lifecycle = iota
	lifecyclePlaying
	lifecycleEnding
	lifecycleClosed
)

type participant struct {
	game       *game
	spec       PlayerSpec
	seat       tile.Seat
	seated     bool
	log        *slog.Logger
	conn       Connection
	standIn    play.Option[wire.SeatControlReason]
	decisionID int
	timer      turnTimer
}

type pause struct {
	startsGame   bool
	owing        [tile.SeatCount]bool
	resultsShown int
}

func (p pause) owes(seat tile.Seat) bool {
	return p.owing[seat.Index()]
}

func (p pause) anyOwing() bool {
	for _, owes := range p.owing {
		if owes {
			return true
		}
	}
	return false
}

type game struct {
	m             *Manager
	id            string
	log           *slog.Logger
	timing        *Timing
	clock         Clock
	inbox         chan func()
	ended         chan struct{}
	lifecycle     lifecycle
	participants  []*participant
	engine        engine.Game
	roster        messaging.Roster
	wait          wait
	hasWait       bool
	pause         *pause
	start         store.GameStart
	startRecorded bool
	replay        *messaging.ReplayLog
	pending       delayed
	aiTurn        delayed
	asked         agentRequest
	end           ending

	drawNoticeFrameByDrawingSeat [tile.SeatCount][]byte
}

func newGame(m *Manager, id string, players []PlayerSpec) *game {
	g := &game{
		m:      m,
		id:     id,
		log:    m.log.With("game_id", id),
		timing: &m.cfg.Timing,
		clock:  m.cfg.Clock,
		inbox:  make(chan func()),
		ended:  make(chan struct{}),
	}
	for _, spec := range players {
		g.participants = append(g.participants, &participant{
			game: g, spec: spec, log: g.log, timer: newTurnTimer(g.timing, g.clock),
		})
	}
	g.pending.arm(g.clock, g.timing.PendingGame, func(token uint64) {
		g.post(func() {
			g.guard("pending game timeout failed", func() error { return g.pendingTimedOut(token) })
		})
	})
	return g
}

func (g *game) active() bool {
	return g.lifecycle == lifecyclePending || g.lifecycle == lifecyclePlaying
}

func (g *game) run() {
	for g.active() {
		step := <-g.inbox
		step()
		g.m.inFlight.Done()
	}
	if g.lifecycle == lifecycleEnding {
		g.finish()
	}
}

func (g *game) post(step func()) bool {
	g.m.inFlight.Add(1)
	select {
	case g.inbox <- step:
		return true
	case <-g.ended:
		g.m.inFlight.Done()
		return false
	}
}

func (g *game) postRouted(step func()) bool {
	sent := g.clock.Now()
	return g.post(func() {
		received := g.clock.Now()
		g.m.delays.observe(received, received.Sub(sent))
		step()
	})
}

func (g *game) postAndWait(step func()) bool {
	done := make(chan struct{})
	posted := g.postRouted(func() {
		defer close(done)
		step()
	})
	if posted {
		<-done
	}
	return posted
}

func ask(g *game, question func() bool) (answer, answered bool) {
	reply := make(chan bool, 1)
	posted := g.post(func() {
		var got bool
		defer func() { reply <- got }()
		g.guard("lobby call failed", func() error {
			got = question()
			return nil
		})
	})
	if !posted {
		return false, false
	}
	return <-reply, true
}

type panicError struct {
	value any
	stack string
}

func (e panicError) Error() string {
	return fmt.Sprintf("panic: %v\n%s", e.value, e.stack)
}

func protect(step func() error) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = panicError{value: r, stack: string(debug.Stack())}
		}
	}()
	return step()
}

func (g *game) guard(reason string, step func() error) {
	err := protect(step)
	if err != nil {
		g.fail(reason, err)
	}
}

func (g *game) serve(conn Connection, reason string, step func() error) {
	err := protect(step)
	if err == nil {
		return
	}

	seated := g.participantOf(conn) != nil
	g.fail(reason, err)
	if !seated {
		g.m.evict(conn)
		g.closeEnded(conn, endFailed)
	}
}

func (g *game) fail(reason string, err error) {
	g.log.Error(logGameFailed, "reason", reason, "error", err)
	g.endGame(endFailed, play.Option[store.Result]{})
}

func (g *game) participantOf(conn Connection) *participant {
	for _, p := range g.participants {
		if p.conn != nil && p.conn == conn {
			return p
		}
	}
	return nil
}

func (g *game) connected() iter.Seq[*participant] {
	return func(yield func(*participant) bool) {
		for _, p := range g.participants {
			if p.conn != nil && !yield(p) {
				return
			}
		}
	}
}

func (g *game) connectedCount() int {
	count := 0
	for range g.connected() {
		count++
	}
	return count
}

func (g *game) othersThan(p *participant) iter.Seq[*participant] {
	return func(yield func(*participant) bool) {
		for other := range g.connected() {
			if other != p && !yield(other) {
				return
			}
		}
	}
}

func (g *game) atSeat(seat tile.Seat) *participant {
	for _, p := range g.participants {
		if p.seated && p.seat == seat {
			return p
		}
	}
	return nil
}

func (g *game) isAISeat(seat tile.Seat) bool {
	p := g.atSeat(seat)
	return p == nil || p.conn == nil
}
