package session

import (
	"strconv"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func (g *game) pauseTimeout() time.Duration {
	if g.pause.startsGame {
		return g.timing.GameStartConfirm
	}
	return g.timing.RoundAdvance * time.Duration(g.pause.resultsShown)
}

func (g *game) stopTimerAt(seat tile.Seat) {
	if p := g.atSeat(seat); p != nil {
		p.timer.stop()
	}
}

func (g *game) startWaitTimers() {
	for _, p := range g.connected() {
		switch {
		case g.pause != nil && g.pause.owes(p.seat):
			p.timer.startFixed(g.pauseTimeout(), g.timerFired(p, timeoutPause))
		case g.pause != nil || !g.wait.awaits(p.seat):
		case g.wait.kind == waitTurn:
			p.timer.startDecision(g.timerFired(p, timeoutTurn))
		default:
			p.timer.startDecision(g.timerFired(p, timeoutMeld))
		}
	}
}

func (g *game) timerFired(p *participant, kind timeoutKind) func(token uint64) {
	reason := timeoutFailure(kind)
	return func(token uint64) {
		g.post(func() {
			g.guard(reason, func() error { return g.timedOut(p, kind, token) })
		})
	}
}

func timeoutFailure(kind timeoutKind) string {
	switch kind {
	case timeoutTurn:
		return "turn timeout failed"
	case timeoutMeld:
		return "meld timeout failed"
	case timeoutPause:
	}
	return "round_advance timeout failed"
}

func (g *game) timedOut(p *participant, kind timeoutKind, token uint64) error {
	if !p.timer.running.claim(token) {
		return nil
	}
	if kind == timeoutPause {
		err := g.confirmPause(p.seat)
		if err != nil {
			return err
		}
		g.m.stats.pauseTimeouts.Add(1)
		return nil
	}

	action, ok := g.engine.DefaultAction(p.seat)
	if !ok {
		return errNoDefault
	}
	message, counter := logTurnTimeout, &g.m.stats.turnTimeouts
	if kind == timeoutMeld {
		message, counter = logMeldTimeout, &g.m.stats.meldTimeouts
	}
	g.seatLog(p).Info(message, "action", actionName(action))
	events, err := g.requireAct(p.seat, action)
	if err != nil {
		return err
	}
	counter.Add(1)
	return g.followEngine(events, play.Some(p.seat))
}

func (g *game) playAIPlayers() error {
	for g.lifecycle == lifecyclePlaying && !g.aiTurn.armed {
		var aiSeats []tile.Seat
		for _, seat := range g.wait.seats {
			if g.isAISeat(seat) {
				aiSeats = append(aiSeats, seat)
			}
		}
		if len(aiSeats) == 0 {
			return nil
		}

		if g.wait.kind == waitTurn && g.timing.AITurnDelay > 0 {
			g.aiTurn.arm(g.clock, g.timing.AITurnDelay, func(token uint64) {
				g.post(func() {
					g.guard("AI turn failed", func() error { return g.aiTurnDue(token) })
				})
			})
			return nil
		}
		err := g.playAIPlayer(aiSeats[0])
		if err != nil {
			return err
		}
	}
	return nil
}

func (g *game) aiTurnDue(token uint64) error {
	if !g.aiTurn.claim(token) {
		return nil
	}
	err := g.playAIPlayer(g.wait.seats[0])
	if err != nil {
		return err
	}
	return g.playAIPlayers()
}

func (g *game) playAIPlayer(seat tile.Seat) error {
	if !g.isAISeat(seat) {
		return errNotAISeat
	}
	decision, ok := g.engine.Decision(seat)
	if !ok {
		return errNoDecision
	}

	g.log.Debug("AI player action", "ai_seat", seat.Index(), "action", actionName(decision.Default))
	events, err := g.requireAct(seat, decision.Default)
	if err != nil {
		return err
	}
	return g.applyUpdate(events, play.Some(seat))
}

func (g *game) confirmPause(seat tile.Seat) error {
	if g.pause == nil || !g.pause.owes(seat) {
		return nil
	}
	g.stopTimerAt(seat)
	g.pause.owing[seat.Index()] = false
	if g.pause.anyOwing() {
		return nil
	}

	ended := *g.pause
	g.pause = nil
	if ended.startsGame {
		return g.beginRound(play.Some(seat))
	}
	next, events, refusal := g.engine.DealNextRound()
	if refusal.OK {
		return errRefusedDeal
	}
	g.engine = next
	return g.followEngine(events, play.Some(seat))
}

func (g *game) gameAction(conn Connection, message messaging.GameActionMessage) error {
	p := g.participantOf(conn)
	if p == nil {
		return nil
	}
	if g.lifecycle == lifecyclePending {
		sendSessionError(g.log, conn, messaging.SessionGameNotStarted, "Game has not started yet")
		return nil
	}
	if message.Action == messaging.GameActionConfirmRound {
		return g.confirmRound(p, message.WaitID)
	}
	if !message.Play.OK {
		return errNoEngineAction
	}

	action := message.Play.Value
	if !g.wait.awaits(p.seat) || message.WaitID != p.decisionID {
		return g.staleAction(p, actionName(action), message.WaitID)
	}
	if message.Called.OK && g.mismatchesOpenCall(p.seat, message.Called.Value) {
		g.seatLog(p).Warn(logCalledTileMismatch, "action", actionName(action))
		return send(conn, messaging.CalledTileMismatch(action, message.WaitID).Payload())
	}

	next, events, refusal := g.engine.Act(p.seat, action)
	if !refusal.OK {
		g.engine = next
		return g.followEngine(events, play.Some(p.seat))
	}
	refused, answerable := messaging.RefusalError(action, refusal.Value, message.WaitID)
	if !answerable {
		return g.kick(p, conn, action, refusal.Value)
	}
	return send(conn, refused.Payload())
}

func (g *game) mismatchesOpenCall(seat tile.Seat, called tile.TileID) bool {
	decision, ok := g.engine.Decision(seat)
	if !ok {
		return false
	}
	call, isCall := decision.Context.(play.Call)
	return isCall && call.Tile != called
}

func (g *game) confirmRound(p *participant, waitID int) error {
	if g.pause == nil || !g.pause.owes(p.seat) || waitID != p.decisionID {
		return g.staleAction(p, "confirm_round", waitID)
	}
	return g.confirmPause(p.seat)
}

func (g *game) staleAction(p *participant, action string, waitID int) error {
	g.seatLog(p).Info(logStaleAction, "action", action, "wait_id", waitID)
	return send(p.conn, messaging.StaleAction(waitID).Payload())
}

func (g *game) kick(p *participant, conn Connection, action play.Action, refusal play.Refusal) error {
	g.seatLog(p).Warn(logInvalidAction, "action", actionName(action), "reason", refusal.Code.String())
	g.m.mu.Lock()
	g.m.evictLocked(conn)
	g.m.mu.Unlock()

	err := g.disconnected(p, conn)
	if err != nil {
		return err
	}
	conn.Close(CloseInvalidAction, "invalid_game_action")
	return nil
}

func (g *game) disconnected(p *participant, conn Connection) error {
	if p.conn != conn {
		return nil
	}
	p.conn = nil
	g.log.Info("player left game", "player_name", p.spec.Name)
	if g.lifecycle != lifecyclePlaying {
		return nil
	}
	return g.releaseSeat(p)
}

func (g *game) releaseSeat(p *participant) error {
	p.timer.stop()
	if len(g.connected()) == 0 {
		g.endGame(endAbandoned, play.Option[store.Result]{})
		return nil
	}

	err := g.handOver(p, play.Some(wire.SeatControlLeft))
	if err != nil {
		return err
	}
	err = g.playAIPlayers()
	if err != nil {
		return err
	}
	return g.confirmPause(p.seat)
}

func (g *game) handOver(p *participant, standIn play.Option[wire.SeatControlReason]) error {
	p.standIn = standIn
	if standIn.OK {
		g.m.stats.aiReplacements.Add(1)
	}
	if g.replay != nil {
		g.replay.recordSeatControl(p.seat, standIn)
	}
	return g.broadcast(messaging.SeatControl(p.seat, standIn))
}

func actionName(action play.Action) string {
	name := "none"
	switch action.Kind() {
	case play.ActionDiscard:
		name = "discard"
	case play.ActionRiichi:
		name = "riichi"
	case play.ActionTsumo:
		name = "tsumo"
	case play.ActionRon:
		name = "ron"
	case play.ActionKyuushu:
		name = "kyuushu"
	case play.ActionPass:
		name = "pass"
	case play.ActionPon:
		name = "pon"
	case play.ActionChi:
		name = "chi"
	case play.ActionKan:
		name = "kan"
	}
	if id, ok := action.Tile(); ok {
		return name + " " + strconv.Itoa(id.Index())
	}
	return name
}
