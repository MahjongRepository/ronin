package session

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// Reconnect binds a connection to the participant of a playing game its verified ticket names and
// sends it the seat's state. A participant who left takes its seat back from its AI player: the
// others get seat_control, and a turn the AI player had not played yet becomes the participant's
// new decision: one the seat left running keeps its original deadline and bank, any other is
// timed from the reconnect. A participant still bound to a connection has that connection
// replaced instead, closed with 4002, and its wait, timers and bank carry on.
// A ticket of no live game, of another game than the connection's, of a pending game or a
// connection already bound is answered why; a connection the session evicted, nothing.
func (m *Manager) Reconnect(conn Connection, ticket string) {
	g, refused, registered := m.reconnecting(conn, ticket)
	switch {
	case !registered:
		return
	case refused.OK:
		sendSessionError(m.log, conn, refused.Value.code, refused.Value.message)
		return
	}
	posted := g.postAndWait(func() {
		g.serve(conn, "reconnect failed", func() error { return g.reconnect(conn, ticket) })
	})
	if !posted {
		sendSessionError(m.log, conn, messaging.SessionReconnectNoSession, noLiveGame)
	}
}

const noLiveGame = "No live game for this ticket"

// Resync sends the participant a connection is bound to its seat's state again, as a reconnect
// does, on the same connection: nothing changes hands and nobody else hears of it, and the wait,
// its timers and the bank carry on. A connection bound to no participant is answered not_in_game,
// one the session evicted nothing, and a pending game game_not_started.
func (m *Manager) Resync(conn Connection) {
	g := m.boundGame(conn)
	if g == nil {
		return
	}
	g.postRouted(func() {
		g.serve(conn, "resync failed", func() error { return g.resync(conn) })
	})
}

func (g *game) reconnect(conn Connection, ticket string) error {
	if g.lifecycle == lifecyclePending {
		sendSessionError(g.log, conn, messaging.SessionReconnectRetryLater, "Game has not started yet, retry shortly")
		return nil
	}
	if !g.active() {
		sendSessionError(g.log, conn, messaging.SessionReconnectNoSession, noLiveGame)
		return nil
	}

	b := g.m.bindReconnecting(g, conn, ticket)
	switch {
	case !b.registered:
		return nil
	case b.refused.OK:
		sendSessionError(g.log, conn, b.refused.Value.code, b.refused.Value.message)
		return nil
	}

	p, message := b.participant, logConnectionTakenOver
	if b.replaced != nil {
		g.closeReplaced(p, b.replaced, conn)
	} else {
		err := g.takeSeatBack(p)
		if err != nil {
			return err
		}
		g.m.stats.reconnects.Add(1)
		message = logPlayerReconnected
	}

	err := g.sendSeatState(p, conn)
	if err != nil {
		return err
	}
	p.log.Info(message)
	return nil
}

func (g *game) takeSeatBack(p *participant) error {
	if g.holdsGameEnd() {
		return nil
	}
	err := g.handOver(p, play.Option[wire.SeatControlReason]{})
	if err != nil {
		return err
	}
	if !g.hold.held() {
		g.takeBackDecision(p)
	}
	return nil
}

func (g *game) takeBackDecision(p *participant) {
	if g.asked.inFlight() && g.asked.seat == p.seat {
		g.asked.invalidate()
		g.playAIPlayers()
	}
	if !g.wait.awaits(p.seat) {
		return
	}
	g.aiTurn.cancel()
	p.decisionID++
	if p.timer.suspended.OK {
		p.timer.resume(g.decisionTimerFired(p))
		return
	}
	g.startDecisionTimer(p)
}

func (g *game) resync(conn Connection) error {
	p := g.participantOf(conn)
	if p == nil {
		return nil
	}
	if g.lifecycle == lifecyclePending {
		sendSessionError(g.log, conn, messaging.SessionGameNotStarted, "Game has not started yet")
		return nil
	}

	err := g.sendSeatState(p, conn)
	if err != nil {
		return err
	}
	g.m.stats.resyncs.Add(1)
	p.log.Info("seat resynced")
	return nil
}

func (g *game) sendSeatState(p *participant, conn Connection) error {
	view := g.shownView(p.seat)
	var standIns [tile.SeatCount]play.Option[wire.SeatControlReason]
	for _, other := range g.participants {
		standIns[other.seat.Index()] = other.standIn
	}
	snapshot, err := messaging.ReconnectionPayload(view.Record, g.roster, standIns)
	if err != nil {
		return err
	}

	err = send(conn, messaging.GameReconnected(snapshot, p.decisionID, g.pausePart(p), g.timerSettings(p)))
	if err != nil {
		return err
	}
	if !view.Decision.OK {
		return nil
	}
	opening := messaging.BuildOpening(view.Decision.Value)
	return send(conn, messaging.StampOpening(opening.Payload, p.decisionID, seconds(p.timer.bank), p.timer.elapsed()))
}

func (g *game) pausePart(p *participant) play.Option[messaging.Pause] {
	if g.pause == nil {
		return play.Option[messaging.Pause]{}
	}
	part := messaging.Pause{Owed: g.pause.owes(p.seat)}
	if elapsed := p.timer.elapsed(); part.Owed && elapsed.OK {
		part.Timer = play.Some(messaging.PauseTimer{Elapsed: elapsed.Value, Timeout: seconds(g.pauseTimeout())})
	}
	return play.Some(part)
}

func (g *game) disconnected(p *participant, conn Connection) error {
	if p.conn != conn {
		return nil
	}

	p.conn = nil
	p.log.Info("player left game", "player_name", p.spec.Name)
	switch {
	case g.holdsGameEnd() && g.connectedCount() == 0:
		return g.showHeld()
	case g.holdsGameEnd(), g.lifecycle != lifecyclePlaying:
		return nil
	}
	return g.releaseSeat(p)
}

func (g *game) releaseSeat(p *participant) error {
	p.timer.suspend()
	if g.connectedCount() == 0 {
		g.endGame(endAbandoned, play.Option[store.Result]{})
		return nil
	}

	err := g.handOver(p, play.Some(wire.SeatControlLeft))
	if err != nil {
		return err
	}
	g.playAIPlayers()
	return g.confirmPause(p.seat)
}

func (g *game) handOver(p *participant, standIn play.Option[wire.SeatControlReason]) error {
	p.standIn = standIn
	if standIn.OK {
		g.m.stats.aiReplacements.Add(1)
	}
	if g.replay != nil {
		g.replay.AddSeatControl(p.seat, standIn)
		g.observed.follow(g.replay, g.clock.Now())
	}
	return g.broadcastTo(g.othersThan(p), messaging.SeatControl(p.seat, standIn))
}
