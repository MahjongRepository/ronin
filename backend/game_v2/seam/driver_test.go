package seam_test

import (
	"fmt"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type eventSink interface {
	record(event play.Emitted) error
}

type noSink struct{}

func (noSink) record(play.Emitted) error {
	return nil
}

type agentFailedError struct {
	seat tile.Seat
	err  error
}

func (e agentFailedError) Error() string {
	return "the agent at seat " + strconv.Itoa(e.seat.Index()) + " failed: " + e.err.Error()
}

func (e agentFailedError) Unwrap() error {
	return e.err
}

type refusedError struct {
	seat    tile.Seat
	action  play.Action
	refusal play.Refusal
}

func (e refusedError) Error() string {
	return fmt.Sprintf("the engine refused %+v from seat %d: %v", e.action, e.seat.Index(), e.refusal.Code)
}

type stepLimitError struct{}

func (stepLimitError) Error() string {
	return "play did not end within the step limit"
}

type invariantError struct {
	step int
	err  error
}

func (e invariantError) Error() string {
	return "invariant broken after step " + strconv.Itoa(e.step) + ": " + e.err.Error()
}

func (e invariantError) Unwrap() error {
	return e.err
}

type sinkFailedError struct {
	err error
}

func (e sinkFailedError) Error() string {
	return "the event sink failed: " + e.err.Error()
}

func (e sinkFailedError) Unwrap() error {
	return e.err
}

type engineBrokeError struct {
	reason string
}

func (e engineBrokeError) Error() string {
	return "the engine broke its contract: " + e.reason
}

type agents = [tile.SeatCount]agent

func deliverEvents(batch []play.Emitted, seated agents, sink eventSink) error {
	for _, event := range batch {
		if err := sink.record(event); err != nil {
			return sinkFailedError{err: err}
		}
	}

	for _, event := range batch {
		for _, s := range tile.Seats() {
			if !event.To.Includes(s) {
				continue
			}

			if err := seated[s.Index()].observe(event); err != nil {
				return agentFailedError{seat: s, err: err}
			}
		}
	}

	return nil
}

type until uint8

const (
	untilRoundOver until = iota + 1
	untilGameOver
)

type checking bool

const (
	checkOff        checking = false
	checkEveryBatch checking = true
)

func playRound(g *engine.Game, initial []play.Emitted, seated agents, sink eventSink) error {
	if err := deliverEvents(initial, seated, sink); err != nil {
		return err
	}

	return playUntil(g, seated, sink, maxRoundSteps, untilRoundOver, checkOff)
}

func playGame(g *engine.Game, initial []play.Emitted, seated agents, sink eventSink, maxSteps int) (play.Standings, error) {
	if err := deliverEvents(initial, seated, sink); err != nil {
		return play.Standings{}, err
	}

	if err := playUntil(g, seated, sink, maxSteps, untilGameOver, checkOff); err != nil {
		return play.Standings{}, err
	}

	return standingsOf(*g)
}

func playGameChecked(g *engine.Game, initial []play.Emitted, seated agents, sink eventSink, maxSteps int) (play.Standings, error) {
	if err := deliverEvents(initial, seated, sink); err != nil {
		return play.Standings{}, err
	}

	if err := check(*g, 0); err != nil {
		return play.Standings{}, err
	}

	if err := playUntil(g, seated, sink, maxSteps, untilGameOver, checkEveryBatch); err != nil {
		return play.Standings{}, err
	}

	return standingsOf(*g)
}

func standingsOf(g engine.Game) (play.Standings, error) {
	standings := g.Standings()
	if !standings.OK {
		return play.Standings{}, engineBrokeError{reason: "a game over has no standings"}
	}

	return standings.Value, nil
}

func check(g engine.Game, step int) error {
	if err := g.CheckInvariants(); err != nil {
		return invariantError{step: step, err: err}
	}

	return nil
}

func playUntil(g *engine.Game, seated agents, sink eventSink, maxSteps int, end until, checked checking) error {
	delivered := func(step int) error {
		if checked == checkOff {
			return nil
		}

		return check(*g, step)
	}

	for step := 1; step <= maxSteps; step++ {
		var s tile.Seat
		switch awaiting := g.Awaiting().(type) {
		case play.AwaitingRoundOver:
			if end == untilRoundOver {
				return nil
			}

			if err := dealNext(g, seated, sink); err != nil {
				return err
			}

			if err := delivered(step); err != nil {
				return err
			}

			continue
		case play.AwaitingDealt:
			if err := begin(g, seated, sink); err != nil {
				return err
			}

			if err := delivered(step); err != nil {
				return err
			}

			continue
		case play.AwaitingTurn:
			s = awaiting.Seat
		case play.AwaitingCall:
			s = awaiting.Seats[0]
		case play.AwaitingGameOver:
			return nil
		}

		batch, err := answer(g, s, seated[s.Index()])
		if err != nil {
			return err
		}

		if deliverErr := deliverEvents(batch, seated, sink); deliverErr != nil {
			return deliverErr
		}

		if deliveredErr := delivered(step); deliveredErr != nil {
			return deliveredErr
		}
	}

	switch g.Awaiting().(type) {
	case play.AwaitingGameOver:
		return nil
	case play.AwaitingRoundOver:
		if end == untilRoundOver {
			return nil
		}
	case play.AwaitingDealt, play.AwaitingTurn, play.AwaitingCall:
	}

	return stepLimitError{}
}

func dealNext(g *engine.Game, seated agents, sink eventSink) error {
	next, events, refusal := g.DealNextRound()
	if refusal.OK {
		return engineBrokeError{reason: "a game awaiting its next round refused to deal it"}
	}

	*g = next
	return deliverEvents(events, seated, sink)
}

func begin(g *engine.Game, seated agents, sink eventSink) error {
	next, events, refusal := g.Begin()
	if refusal.OK {
		return engineBrokeError{reason: "a dealt game refused its dealer's first draw"}
	}

	*g = next
	return deliverEvents(events, seated, sink)
}

func answer(g *engine.Game, s tile.Seat, seated agent) ([]play.Emitted, error) {
	decision, ok := g.Decision(s)
	if !ok {
		return nil, engineBrokeError{reason: "an awaited seat has no decision"}
	}

	action, err := seated.decide(decision)
	if err != nil {
		return nil, agentFailedError{seat: s, err: err}
	}

	next, events, refusal := g.Act(s, action)
	if refusal.OK {
		return nil, refusedError{seat: s, action: action, refusal: refusal.Value}
	}

	*g = next
	return events, nil
}
