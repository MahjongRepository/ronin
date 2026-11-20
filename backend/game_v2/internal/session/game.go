package session

import (
	"errors"
	"fmt"
	"log/slog"
	"runtime/debug"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	logAuthTimeout        = "auth timeout, closing unauthenticated connection"
	logTurnTimeout        = "turn timeout, auto-discarding"
	logMeldTimeout        = "meld timeout, auto-passing"
	logStaleAction        = "stale game action"
	logInvalidAction      = "invalid game action"
	logCalledTileMismatch = "invalid call: tile_id mismatch"
	logGameFailed         = "game failed"
)

type lifecycle uint8

const (
	lifecyclePending lifecycle = iota
	lifecyclePlaying
	lifecycleEnding
	lifecycleClosed
)

type endReason uint8

const (
	endCompleted endReason = iota
	endAbandoned
	endFailed
)

type participant struct {
	game       *game
	spec       PlayerSpec
	seat       tile.Seat
	seated     bool
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

type ending struct {
	reason     endReason
	conns      []Connection
	keepReplay bool
	records    []wire.Map
	result     play.Option[store.Result]
	endedAt    time.Time
}

type game struct {
	m            *Manager
	id           string
	log          *slog.Logger
	timing       *Timing
	clock        Clock
	inbox        chan func()
	ended        chan struct{}
	lifecycle    lifecycle
	participants []*participant
	engine       engine.Game
	roster       messaging.Roster
	wait         wait
	hasWait      bool
	pause        *pause
	holdingDraw  bool
	held         []play.Emitted
	dealt        [tile.SeatCount]play.RoundStarted
	start        store.GameStart
	startWritten chan struct{}
	replay       *replayLog
	pending      delayed
	aiTurn       delayed
	end          ending
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
			game: g, spec: spec, timer: newTurnTimer(g.timing, g.clock),
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
	}
	if g.lifecycle == lifecycleEnding {
		g.finish()
	}
}

func (g *game) post(step func()) bool {
	select {
	case g.inbox <- step:
		return true
	case <-g.ended:
		return false
	}
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

func (g *game) connected() []*participant {
	var connected []*participant
	for _, p := range g.participants {
		if p.conn != nil {
			connected = append(connected, p)
		}
	}
	return connected
}

func (g *game) othersThan(p *participant) []*participant {
	var others []*participant
	for _, other := range g.connected() {
		if other != p {
			others = append(others, other)
		}
	}
	return others
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

func (g *game) seatLog(p *participant) *slog.Logger {
	return g.log.With("seat", p.seat.Index())
}

func (g *game) withdraw() bool {
	if g.lifecycle != lifecyclePending || len(g.connected()) > 0 {
		g.log.Warn("withdrawn game kept, a player already joined it")
		return false
	}

	g.log.Info("pending game withdrawn")
	g.m.markWithdrawn(g.id)
	g.endGame(endAbandoned, play.Option[store.Result]{})
	return true
}

func (g *game) endGame(reason endReason, result play.Option[store.Result]) {
	if !g.active() {
		return
	}

	g.lifecycle = lifecycleEnding
	conns := make([]Connection, 0, len(g.participants))
	for _, p := range g.connected() {
		conns = append(conns, p.conn)
	}
	g.end = ending{reason: reason, conns: conns, result: result, endedAt: g.clock.Now()}
	if g.replay != nil && reason != endAbandoned {
		g.end.keepReplay, g.end.records = true, g.replay.records
	}
	g.replay = nil

	g.release(conns)
	for _, p := range g.participants {
		p.timer.cancel()
		p.conn = nil
	}
	g.pending.cancel()
	g.aiTurn.cancel()
	close(g.ended)
}

func (g *game) release(conns []Connection) {
	m := g.m
	m.mu.Lock()
	defer m.mu.Unlock()

	if l := m.games[g.id]; l != nil && l.game == g {
		delete(m.games, g.id)
	}
	for _, p := range g.participants {
		if l := m.tickets[p.spec.Ticket]; l != nil && l.game == g {
			delete(m.tickets, p.spec.Ticket)
		}
	}
	for _, conn := range conns {
		m.evictLocked(conn)
	}
}

func (g *game) vanish() {
	if !g.active() {
		return
	}
	g.lifecycle = lifecycleClosed
	for _, p := range g.participants {
		p.timer.cancel()
	}
	g.pending.cancel()
	g.aiTurn.cancel()
	close(g.ended)
}

func (g *game) finish() {
	e := g.end
	reason := e.reason
	if e.keepReplay {
		err := protect(func() error { return g.saveReplay(e.records) })
		if err != nil {
			g.log.Error("save the replay of a finished game", "error", err)
			reason = endFailed
		} else {
			g.log.Info("saved replay")
		}
	}

	if g.startWritten != nil {
		<-g.startWritten
		err := protect(func() error { return g.recordFinish(reason, e) })
		if err != nil {
			g.log.Error("record the finish of a game", "error", err)
		}
	}

	for _, conn := range e.conns {
		g.closeEnded(conn, reason)
	}
	g.lifecycle = lifecycleClosed
}

func (g *game) closeEnded(conn Connection, reason endReason) {
	err := protect(func() error {
		if reason == endCompleted {
			conn.Close(CloseGameEnded, "game_ended")
			return nil
		}
		return closeWithInternalError(conn)
	})
	if err != nil {
		g.log.Error("close a connection of an ended game", "error", err)
	}
}

func (g *game) saveReplay(records []wire.Map) error {
	content, err := encodeReplay(records)
	if err != nil {
		return err
	}
	return g.m.cfg.Replays.Save(g.id, content)
}

var errNoResult = errors.New("a completed game has no result")

func (g *game) recordFinish(reason endReason, e ending) error {
	db, ctx := g.m.cfg.DB, g.m.storeCtx
	switch reason {
	case endCompleted:
		if !e.result.OK {
			return errNoResult
		}
		return db.RecordCompleted(ctx, g.start, e.endedAt, e.result.Value)
	case endAbandoned:
		return db.RecordAbandoned(ctx, g.start, e.endedAt)
	case endFailed:
	}
	return db.RecordFailed(ctx, g.start, e.endedAt)
}

func closeWithInternalError(conn Connection) error {
	defer conn.Close(CloseInternalError, "internal_error")
	return send(conn, messaging.SessionError(
		messaging.SessionInternalError, "The game ended on a server error", play.Option[int]{}))
}
