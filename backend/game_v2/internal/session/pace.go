package session

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"slices"
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
	for p := range g.connected() {
		switch {
		case g.pause != nil && g.pause.owes(p.seat):
			p.timer.startFixed(g.pauseTimeout(), g.timerFired(p, timeoutPause))
		case g.pause != nil || !g.wait.awaits(p.seat):
		default:
			g.startDecisionTimer(p)
		}
	}
}

func (g *game) startDecisionTimer(p *participant) {
	p.timer.startDecision(g.decisionTimerFired(p))
}

func (g *game) decisionTimerFired(p *participant) func(token uint64) {
	kind := timeoutMeld
	if g.wait.kind == waitTurn {
		kind = timeoutTurn
	}
	return g.timerFired(p, kind)
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
		g.m.stats.roundAdvanceTimeouts.Add(1)
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
	p.log.Info(message, "action", actionName(action))
	events, err := g.requireAct(p.seat, action)
	if err != nil {
		return err
	}
	counter.Add(1)
	return g.followEngine(events, play.Some(p.seat))
}

type agentRequest struct {
	deadline delayed
	seat     tile.Seat
	cancel   context.CancelFunc
}

type agentAnswer struct {
	token    uint64
	seat     tile.Seat
	action   play.Action
	err      error
	panicked error
}

func (r *agentRequest) inFlight() bool {
	return r.deadline.armed
}

func (r *agentRequest) take(token uint64) bool {
	if !r.inFlight() || token != r.deadline.token {
		return false
	}
	r.invalidate()
	return true
}

func (r *agentRequest) invalidate() {
	if r.inFlight() {
		r.deadline.cancel()
		r.cancel()
	}
}

var (
	errAgentDeadline = errors.New("the AI agent gave no answer within the base turn time")
	errAgentIllegal  = errors.New("the AI agent answered an action its decision does not offer")
)

func (g *game) playAIPlayers() {
	if g.lifecycle != lifecyclePlaying || g.aiTurn.armed || g.asked.inFlight() {
		return
	}
	index := slices.IndexFunc(g.wait.seats, g.isAISeat)
	if index < 0 {
		return
	}

	if g.wait.kind == waitTurn && g.timing.AITurnDelay > 0 {
		g.aiTurn.arm(g.clock, g.timing.AITurnDelay, func(token uint64) {
			g.post(func() {
				g.guard("AI turn failed", func() error { return g.aiTurnDue(token) })
			})
		})
		return
	}
	g.askAgent(g.wait.seats[index])
}

func (g *game) aiTurnDue(token uint64) error {
	if !g.aiTurn.claim(token) {
		return nil
	}
	seat := g.wait.seats[0]
	if !g.isAISeat(seat) {
		return errNotAISeat
	}
	g.askAgent(seat)
	return nil
}

func (g *game) askAgent(seat tile.Seat) {
	view := g.engine.View(seat)
	ctx, cancel := context.WithCancel(context.Background())
	g.asked.seat, g.asked.cancel = seat, cancel
	g.asked.deadline.arm(g.clock, g.timing.BaseTurn, func(token uint64) {
		g.post(func() {
			g.guard("AI player failed", func() error {
				return g.agentAnswered(agentAnswer{token: token, seat: seat, err: errAgentDeadline})
			})
		})
	})
	token := g.asked.deadline.token

	agent := g.m.cfg.Agent
	g.m.inFlight.Add(1)
	g.m.wg.Go(func() {
		defer g.m.inFlight.Done()
		answer := agentAnswer{token: token, seat: seat}
		answer.panicked = protect(func() error {
			answer.action, answer.err = agent.Decide(ctx, view)
			return nil
		})
		g.post(func() {
			g.guard("AI player failed", func() error { return g.agentAnswered(answer) })
		})
	})
}

func (g *game) agentAnswered(answer agentAnswer) error {
	if !g.asked.take(answer.token) || !g.wait.awaits(answer.seat) || !g.isAISeat(answer.seat) {
		return nil
	}
	if answer.panicked != nil {
		return fmt.Errorf("the AI agent panicked: %w", answer.panicked)
	}
	seat := answer.seat
	decision, ok := g.engine.Decision(seat)
	if !ok {
		return errNoDecision
	}

	failure := answer.err
	if failure == nil {
		next, events, refusal := g.engine.Act(seat, answer.action)
		if !refusal.OK {
			g.engine = next
			return g.followAIPlayer(seat, answer.action, events)
		}
		if slices.Contains(decision.Legal, answer.action) {
			return fmt.Errorf("the engine refused an offered AI answer %s: %s: %s",
				actionName(answer.action), refusal.Value.Kind, refusal.Value.Code)
		}
		failure = fmt.Errorf("%w: %s", errAgentIllegal, actionName(answer.action))
	}

	g.log.Warn(logAgentFallback, "ai_seat", seat.Index(), "error", failure)
	events, err := g.requireAct(seat, decision.Default)
	if err != nil {
		return err
	}
	return g.followAIPlayer(seat, decision.Default, events)
}

func (g *game) followAIPlayer(seat tile.Seat, action play.Action, events []play.Emitted) error {
	if g.log.Enabled(context.Background(), slog.LevelDebug) {
		g.log.Debug("AI player action", "ai_seat", seat.Index(), "action", actionName(action))
	}
	return g.followEngine(events, play.Some(seat))
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
		return g.begin(play.Some(seat))
	}
	next, events, refusal := g.engine.DealNextRound()
	if refusal.OK {
		return errRefusedDeal
	}
	if _, dealt := next.Awaiting().(play.AwaitingDealt); dealt {
		var drew []play.Emitted
		next, drew, refusal = next.Begin()
		if refusal.OK {
			return errRefusedBegin
		}
		events = append(events, drew...)
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
		p.log.Warn(logCalledTileMismatch, "action", actionName(action))
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
	p.log.Info(logStaleAction, "action", action, "wait_id", waitID)
	return send(p.conn, messaging.StaleAction(waitID).Payload())
}

func (g *game) kick(p *participant, conn Connection, action play.Action, refusal play.Refusal) error {
	p.log.Warn(logInvalidAction, "action", actionName(action), "reason", refusal.Code.String())
	g.m.evict(conn)
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
	p.log.Info("player left game", "player_name", p.spec.Name)
	if g.lifecycle != lifecyclePlaying {
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
	}
	return g.broadcastTo(g.othersThan(p), messaging.SeatControl(p.seat, standIn))
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
