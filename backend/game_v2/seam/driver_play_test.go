package seam_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	maxRoundSteps = 200
	maxGameSteps  = 20000
)

var (
	errObserveFailed = errors.New("the agent failed to observe its deal")
	errRecordFailed  = errors.New("the sink failed to record its second event")
)

func tsumogiriAgents() agents {
	return agents{tsumogiri{}, tsumogiri{}, tsumogiri{}, tsumogiri{}}
}

func lastResult(t *testing.T, g engine.Game) play.RoundResult {
	t.Helper()
	history := g.View(seat(t, 0)).Record.History
	if len(history) == 0 {
		t.Fatal("no round has finished")
	}
	return history[len(history)-1].Result
}

func TestPlayRound_WhenTsumogiriAgentsPlayASeededRound_ShouldEndInAnExhaustiveDraw(t *testing.T) {
	g, initial := newGame(t, seededSetup(t, "ab"))

	err := playRound(&g, initial, tsumogiriAgents(), noSink{})

	assertEqual(t, "error", err, nil)
	record := g.View(seat(t, 0)).Record
	assertEqual(t, "phase", record.Phase, play.PhaseRoundOver)
	assertEqual(t, "rounds", len(record.History), 1)
	if _, ok := lastResult(t, g).(play.ExhaustiveDraw); !ok {
		t.Errorf("result = %#v, want an exhaustive draw", lastResult(t, g))
	}
	assertEqual(t, "invariants", g.CheckInvariants(), nil)
}

func TestDefaultAction_WhenPlayedByEveryAwaitedSeatThroughASeededRound_ShouldBeAcceptedAndKeepEveryTileOwned(t *testing.T) {
	g, _ := newGame(t, seededSetup(t, "ab"))
	assertEqual(t, "invariants at the start", g.CheckInvariants(), nil)

	steps := 0
	for {
		var seats []tile.Seat
		switch awaiting := g.Awaiting().(type) {
		case play.AwaitingDealt:
			g, _ = begun(t, g)
			continue
		case play.AwaitingTurn:
			seats = []tile.Seat{awaiting.Seat}
		case play.AwaitingCall:
			seats = awaiting.Seats
		case play.AwaitingRoundOver, play.AwaitingGameOver:
		}
		if len(seats) == 0 {
			break
		}
		for _, s := range seats {
			if steps >= maxRoundSteps {
				t.Fatalf("the round did not end in %d steps", maxRoundSteps)
			}
			decision, ok := g.Decision(s)
			if !ok || !slices.Contains(decision.Legal, decision.Default) {
				t.Fatalf("step %d: seat %d has no decision with a legal default", steps, s.Index())
			}
			g, _ = act(t, g, s, decision.Default)
			if err := g.CheckInvariants(); err != nil {
				t.Fatalf("after step %d: %v", steps, err)
			}
			steps++
		}
	}

	assertEqual[play.Awaiting](t, "awaiting", g.Awaiting(), play.AwaitingRoundOver{})
}

type handWatcher struct {
	dealtSeats             []tile.Seat
	dealtHands             [][]tile.TileID
	handsSeenAtFirstChoice play.Option[int]
	decisions              int
}

func (w *handWatcher) observe(event play.Emitted) error {
	if started, ok := event.Event.(play.RoundStarted); ok {
		w.dealtSeats = append(w.dealtSeats, started.Seat)
		w.dealtHands = append(w.dealtHands, started.Hand)
	}
	return nil
}

func (w *handWatcher) decide(decision play.Decision) (play.Action, error) {
	if !w.handsSeenAtFirstChoice.OK {
		w.handsSeenAtFirstChoice = play.Some(len(w.dealtHands))
	}
	w.decisions++
	return decision.Default, nil
}

type recorder struct {
	events []play.Emitted
}

func (r *recorder) record(event play.Emitted) error {
	r.events = append(r.events, event)
	return nil
}

func TestPlayRound_ShouldShowEachAgentItsHandBeforeItDecidesAndTheSinkEveryDealFirst(t *testing.T) {
	g, initial := newGame(t, seededSetup(t, "ab"))
	watchers := [tile.SeatCount]*handWatcher{{}, {}, {}, {}}
	sink := &recorder{}

	err := playRound(&g, initial, agents{watchers[0], watchers[1], watchers[2], watchers[3]}, sink)

	assertEqual(t, "error", err, nil)
	dealt, _ := newGame(t, seededSetup(t, "ab"))
	for _, s := range tile.Seats() {
		watcher := watchers[s.Index()]
		assertEqual(t, "dealt seats", watcher.dealtSeats, []tile.Seat{s})
		assertEqual(t, "dealt hands", watcher.dealtHands, [][]tile.TileID{dealt.View(s).Record.Hand[:handSize]})
		assertEqual(t, "hands seen at the first decision", watcher.handsSeenAtFirstChoice, play.Some(1))
		if watcher.decisions == 0 {
			t.Errorf("seat %d decided nothing", s.Index())
		}
	}

	firstDraw := slices.IndexFunc(sink.events, func(e play.Emitted) bool { _, ok := e.Event.(play.Drew); return ok })
	if firstDraw < 0 {
		t.Fatal("the sink saw no draw")
	}
	var dealtSeats []tile.Seat
	allDealt := 0
	for i, e := range sink.events {
		if started, ok := e.Event.(play.RoundStarted); ok {
			allDealt++
			if i < firstDraw {
				dealtSeats = append(dealtSeats, started.Seat)
			}
		}
	}
	every := tile.Seats()
	assertEqual(t, "seats dealt before the first draw", dealtSeats, every[:])
	assertEqual(t, "deals", allDealt, tile.SeatCount)
}

type unheldDiscarder struct{}

func (unheldDiscarder) observe(play.Emitted) error {
	return nil
}

func (unheldDiscarder) decide(decision play.Decision) (play.Action, error) {
	for _, candidate := range tile.AllTileIDs() {
		if !slices.Contains(decision.Legal, play.DiscardAction(candidate)) {
			return play.DiscardAction(candidate), nil
		}
	}
	return play.Action{}, errors.New("every tile is held")
}

func TestPlayRound_WhenTheEngineRefusesAnAgentsAction_ShouldStopWithoutFallingBackToTheDefault(t *testing.T) {
	g, initial := newGame(t, seededSetup(t, "ab"))
	expected, _ := newGame(t, seededSetup(t, "ab"))
	expected, _ = begun(t, expected)
	dealer := turnSeat(t, expected)

	err := playRound(&g, initial, agents{unheldDiscarder{}, unheldDiscarder{}, unheldDiscarder{}, unheldDiscarder{}}, noSink{})

	var unheld tile.TileID
	for _, candidate := range tile.AllTileIDs() {
		if !slices.Contains(expected.View(dealer).Record.Hand, candidate) {
			unheld = candidate
			break
		}
	}
	assertEqual[error](t, "error", err, refusedError{
		seat:    dealer,
		action:  play.DiscardAction(unheld),
		refusal: play.Refusal{Kind: play.RefusalNotOffered, Code: play.CodeTileNotHeld},
	})
	assertSameGame(t, "after the refusal", g, expected)
}

func TestPlayRound_WhenTsumogiriAgentsPlayADealerTsumoWall_ShouldEndInTheDealersTsumo(t *testing.T) {
	w := startWall{
		hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m1112p"),
			copies(t, 1, "123456789s1234z"),
			copies(t, 2, "123456789s1234z"),
			copies(t, 3, "123456789s1234z"),
		},
		draws: copies(t, 1, "2p"),
	}
	g, initial := newGame(t, fixedSetup(t, w))

	err := playRound(&g, initial, tsumogiriAgents(), noSink{})

	assertEqual(t, "error", err, nil)
	assertEqual(t, "rounds", len(g.View(seat(t, 0)).Record.History), 1)
	tsumo, ok := lastResult(t, g).(play.Tsumo)
	if !ok || tsumo.Win.Winner != seat(t, 0) {
		t.Errorf("result = %#v, want seat 0's tsumo", lastResult(t, g))
	}
}

type failsOnItsDeal struct{}

func (failsOnItsDeal) observe(event play.Emitted) error {
	if _, ok := event.Event.(play.RoundStarted); ok {
		return errObserveFailed
	}
	return nil
}

func (failsOnItsDeal) decide(decision play.Decision) (play.Action, error) {
	return decision.Default, nil
}

func TestDeliverEvents_WhenAnAgentFailsMidBatch_ShouldStillHaveRecordedTheWholeBatch(t *testing.T) {
	_, initial := newGame(t, seededSetup(t, "ab"))
	sink := &recorder{}

	err := deliverEvents(initial, agents{tsumogiri{}, failsOnItsDeal{}, tsumogiri{}, tsumogiri{}}, sink)

	assertEqual[error](t, "error", err, agentFailedError{seat: seat(t, 1), err: errObserveFailed})
	last := initial[len(initial)-1]
	to, single := last.To.Seat()
	if _, dealt := last.Event.(play.RoundStarted); !dealt || !single || to != seat(t, 3) {
		t.Errorf("last initial event = %#v, want seat 3's deal", last)
	}
	assertEqual(t, "recorded", sink.events, initial)
}

type failsOnSecondEvent struct {
	events []play.Emitted
}

func (s *failsOnSecondEvent) record(event play.Emitted) error {
	if len(s.events) == 1 {
		return errRecordFailed
	}
	s.events = append(s.events, event)
	return nil
}

type observer struct {
	events []play.Emitted
}

func (o *observer) observe(event play.Emitted) error {
	o.events = append(o.events, event)
	return nil
}

func (*observer) decide(decision play.Decision) (play.Action, error) {
	return decision.Default, nil
}

func TestDeliverEvents_WhenTheSinkFails_ShouldStopBeforeAnyAgentObservesTheBatch(t *testing.T) {
	_, initial := newGame(t, seededSetup(t, "ab"))
	observers := [tile.SeatCount]*observer{{}, {}, {}, {}}
	sink := &failsOnSecondEvent{}

	err := deliverEvents(initial, agents{observers[0], observers[1], observers[2], observers[3]}, sink)

	assertEqual[error](t, "error", err, sinkFailedError{err: errRecordFailed})
	assertEqual(t, "recorded", sink.events, initial[:1])
	var observed [tile.SeatCount]int
	for i, o := range observers {
		observed[i] = len(o.events)
	}
	assertEqual(t, "observed", observed, [tile.SeatCount]int{})
}

func TestPlayGame_WhenItsFixedWallsRunOut_ShouldEndTheGame(t *testing.T) {
	g, initial := newGame(t, fixedSetup(t, notenWall(t)))

	standings, err := playGame(&g, initial, tsumogiriAgents(), noSink{}, maxRoundSteps)

	assertEqual(t, "error", err, nil)
	assertEqual(t, "cause", standings.Cause, play.EndFixedWallsDealt)
	assertEqual(t, "rounds", len(g.View(seat(t, 0)).Record.History), 1)
}

func TestPlayGameChecked_ShouldEndWithTheStandingsOfTheUncheckedGame(t *testing.T) {
	checked, initial := newGame(t, seededSetup(t, "ab"))
	unchecked, _ := newGame(t, seededSetup(t, "ab"))

	checkedStandings, checkedErr := playGameChecked(&checked, initial, tsumogiriAgents(), noSink{}, maxGameSteps)
	standings, err := playGame(&unchecked, initial, tsumogiriAgents(), noSink{}, maxGameSteps)

	assertEqual(t, "errors", [2]error{checkedErr, err}, [2]error{})
	assertEqual(t, "standings", checkedStandings, standings)
	assertEqual(t, "invariants", checked.CheckInvariants(), nil)
}

func TestPlayGameChecked_WhenTheGameStartsFromAPosition_ShouldCountThePointsItBrings(t *testing.T) {
	setup := seededSetup(t, "ab")
	setup.Start = play.Some(play.StartPosition{
		Scores:       [tile.SeatCount]int{31000, 20000, 26000, 21000},
		RiichiSticks: 2,
		Dealer:       seat(t, 0),
		Wind:         tile.East,
	})
	g, initial := newGame(t, setup)

	standings, err := playGameChecked(&g, initial, tsumogiriAgents(), noSink{}, maxGameSteps)

	assertEqual(t, "error", err, nil)
	assertEqual(t, "final score total", scoreTotal(standings.Scores), tablePoints)
}
