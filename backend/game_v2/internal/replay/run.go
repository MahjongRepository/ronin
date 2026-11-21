package replay

import (
	"errors"
	"fmt"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Step is one step of a run: the game's start or a deal, each with the dealer's first draw that
// follows it, or a seat's action; the events it emitted; and the game after it.
type Step struct {
	Events []play.Emitted
	Game   engine.Game
}

// RefusedError reports an action the engine refused: the action at Index, or a pass Run answered
// for a seat ahead of it, Index then counting the actions before it (all of them after the last).
type RefusedError struct {
	Index   int
	Played  SeatAction
	Refusal play.Refusal
}

func (e RefusedError) Error() string {
	return "action " + strconv.Itoa(e.Index) + " of seat " + strconv.Itoa(e.Played.Seat.Index()) + " refused: " +
		e.Refusal.Kind.String() + ": " + e.Refusal.Code.String()
}

// ActionAfterGameEndError reports actions left once the game is over, from the one at Index.
type ActionAfterGameEndError struct {
	Index int
}

func (e ActionAfterGameEndError) Error() string {
	return "action " + strconv.Itoa(e.Index) + " comes after the game end"
}

var (
	errDealRefused  = errors.New("the engine refused the next round's deal")
	errBeginRefused = errors.New("the engine refused the dealer's first draw")
)

// Run starts a game from setup and plays actions in order, one engine call each, and returns every
// step: the game's start first. Before each action it deals the next round when the last one is
// over, and it passes for every seat an open call prompt still waits on, in seat order, but the
// action's own seat when the action answers the prompt, and after a ron the seats of the rons that
// directly follow it, which answer the same prompt. Once every action is played it passes for the
// seats a prompt still waits on and deals a round that is over.
//
// The error is engine.NewGame's for a setup it refuses, a RefusedError for any action or pass the
// engine refuses, an ActionAfterGameEndError for actions left once the game is over, or an error
// when the engine refuses the next deal or the dealer's first draw.
func Run(setup engine.Setup, actions []SeatAction) ([]Step, error) {
	g, events, err := engine.NewGame(setup)
	if err != nil {
		return nil, fmt.Errorf("start the replayed game: %w", err)
	}
	g, events, err = begun(g, events)
	if err != nil {
		return nil, err
	}

	r := runner{game: g, steps: []Step{{Events: events, Game: g}}}
	for i, action := range actions {
		err = r.prepare(i, actions)
		if err != nil {
			return nil, err
		}
		err = r.play(i, action)
		if err != nil {
			return nil, err
		}
	}

	err = r.pass(len(actions), nil)
	if err != nil {
		return nil, err
	}
	err = r.deal()
	if err != nil {
		return nil, err
	}
	return r.steps, nil
}

type runner struct {
	game  engine.Game
	steps []Step
}

func (r *runner) prepare(index int, actions []SeatAction) error {
	switch r.game.Awaiting().(type) {
	case play.AwaitingTurn:
		return nil
	case play.AwaitingGameOver:
		return ActionAfterGameEndError{Index: index}
	case play.AwaitingCall, play.AwaitingDealt, play.AwaitingRoundOver:
	}

	err := r.deal()
	if err != nil {
		return err
	}
	err = r.pass(index, answering(r.game.Awaiting(), actions[index:]))
	if err != nil {
		return err
	}
	err = r.deal()
	if err != nil {
		return err
	}

	if r.isOver() {
		return ActionAfterGameEndError{Index: index}
	}
	return nil
}

func answering(awaiting play.Awaiting, actions []SeatAction) []tile.Seat {
	call, open := awaiting.(play.AwaitingCall)
	next := actions[0]
	if !open || !slices.Contains(call.Seats, next.Seat) || !next.Action.AnswersCall() ||
		next.Action.Kind() == play.ActionPass {
		return nil
	}

	seats := []tile.Seat{next.Seat}
	if next.Action.Kind() != play.ActionRon {
		return seats
	}
	for _, later := range actions[1:] {
		if later.Action.Kind() != play.ActionRon {
			break
		}
		seats = append(seats, later.Seat)
	}
	return seats
}

func (r *runner) pass(index int, answered []tile.Seat) error {
	call, open := r.game.Awaiting().(play.AwaitingCall)
	if !open {
		return nil
	}

	for _, s := range call.Seats {
		if slices.Contains(answered, s) {
			continue
		}
		if _, still := r.game.Awaiting().(play.AwaitingCall); !still {
			return nil
		}
		err := r.play(index, SeatAction{Seat: s, Action: play.PassAction()})
		if err != nil {
			return err
		}
	}
	return nil
}

func (r *runner) play(index int, action SeatAction) error {
	g, events, refusal := r.game.Act(action.Seat, action.Action)
	if refusal.OK {
		return RefusedError{Index: index, Played: action, Refusal: refusal.Value}
	}
	r.game = g
	r.steps = append(r.steps, Step{Events: events, Game: g})
	return nil
}

func (r *runner) deal() error {
	if _, over := r.game.Awaiting().(play.AwaitingRoundOver); !over {
		return nil
	}
	g, events, refusal := r.game.DealNextRound()
	if refusal.OK {
		return errDealRefused
	}
	g, events, err := begun(g, events)
	if err != nil {
		return err
	}
	r.game = g
	r.steps = append(r.steps, Step{Events: events, Game: g})
	return nil
}

func begun(g engine.Game, events []play.Emitted) (engine.Game, []play.Emitted, error) {
	if _, dealt := g.Awaiting().(play.AwaitingDealt); !dealt {
		return g, events, nil
	}
	next, drew, refusal := g.Begin()
	if refusal.OK {
		return g, nil, errBeginRefused
	}
	return next, append(events, drew...), nil
}

func (r *runner) isOver() bool {
	_, over := r.game.Awaiting().(play.AwaitingGameOver)
	return over
}
