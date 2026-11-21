package session

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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
	if g.lifecycle != lifecyclePlaying || g.hold.held() || g.aiTurn.armed || g.asked.inFlight() {
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
	fallback := disguisedDefault(decision, g.m.cfg.Pick)
	events, err := g.requireAct(seat, fallback)
	if err != nil {
		return err
	}
	return g.followAIPlayer(seat, fallback, events)
}

func (g *game) followAIPlayer(seat tile.Seat, action play.Action, events []play.Emitted) error {
	if g.log.Enabled(context.Background(), slog.LevelDebug) {
		g.log.Debug("AI player action", "ai_seat", seat.Index(), "action", actionName(action))
	}
	return g.followEngine(events, play.Some(seat))
}
