package session

import (
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
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

	decision, ok := g.engine.Decision(p.seat)
	if !ok {
		return errNoDefault
	}
	action := disguisedDefault(decision, g.m.cfg.Pick)
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
