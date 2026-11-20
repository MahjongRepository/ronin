package session

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// Reconnect binds a connection to the participant of a playing game its verified ticket names and
// sends it the seat's state. A participant who left takes its seat back from its AI player: the
// others get seat_control, and a turn the AI player had not played yet becomes the participant's
// new decision, its timer started with the reconnect. A participant still bound to a connection
// has that connection replaced instead, closed with 4002, and its wait, timers and bank carry on.
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

func (m *Manager) reconnecting(conn Connection, ticket string) (*game, play.Option[sessionRefusal], bool) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.registeredLocked(conn) == nil {
		return nil, play.Option[sessionRefusal]{}, false
	}
	switch l := m.tickets[ticket]; {
	case l == nil:
		return nil, play.Some(sessionRefusal{messaging.SessionReconnectNoSession, noLiveGame}), true
	case l.game.id != conn.GameID():
		return nil, play.Some(sessionRefusal{
			messaging.SessionReconnectGameMismatch, "Session token is not valid for this game",
		}), true
	default:
		return l.game, play.Option[sessionRefusal]{}, true
	}
}

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

	b := g.bindReconnecting(conn, ticket)
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
		err := g.handOver(p, play.Option[wire.SeatControlReason]{})
		if err != nil {
			return err
		}
		g.takeBackDecision(p)
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

func (g *game) bindReconnecting(conn Connection, ticket string) seatBinding {
	g.m.mu.Lock()
	defer g.m.mu.Unlock()

	entry := g.m.registeredLocked(conn)
	switch {
	case entry == nil:
		return seatBinding{}
	case entry.bound != nil:
		return seatBinding{registered: true, refused: play.Some(sessionRefusal{
			messaging.SessionReconnectAlreadyActive, "Connection already in a game",
		})}
	}
	p := g.byTicket(ticket)
	return seatBinding{registered: true, participant: p, replaced: g.bindLocked(p, entry)}
}

func (g *game) takeBackDecision(p *participant) {
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
	view := g.engine.View(p.seat)
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
