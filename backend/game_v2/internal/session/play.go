package session

import (
	"errors"
	"fmt"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type waitKind uint8

const (
	waitDealt waitKind = iota
	waitTurn
	waitCall
	waitRoundOver
	waitGameOver
)

type wait struct {
	kind  waitKind
	seats []tile.Seat
}

func waitOf(awaiting play.Awaiting) wait {
	switch a := awaiting.(type) {
	case play.AwaitingTurn:
		return wait{kind: waitTurn, seats: []tile.Seat{a.Seat}}
	case play.AwaitingCall:
		return wait{kind: waitCall, seats: slices.Clone(a.Seats)}
	case play.AwaitingRoundOver:
		return wait{kind: waitRoundOver}
	case play.AwaitingGameOver:
	}
	return wait{kind: waitGameOver}
}

func (w wait) awaits(seat tile.Seat) bool {
	return slices.Contains(w.seats, seat)
}

func opensNewWait(previous, awaiting wait, actor play.Option[tile.Seat]) bool {
	if previous.kind != awaiting.kind {
		return true
	}
	for _, seat := range awaiting.seats {
		if !previous.awaits(seat) || (actor.OK && actor.Value == seat) {
			return true
		}
	}
	return false
}

var (
	errNoDecision     = errors.New("an awaited seat has no decision")
	errNoDefault      = errors.New("a timed out seat is not awaited")
	errNoConnected    = errors.New("a round ended with no connected participant")
	errNotAISeat      = errors.New("an AI answer for a seat a connected participant plays")
	errGameOverNoEnd  = errors.New("the game is over with no game end")
	errNoEngineAction = errors.New("a game action carries no engine action")
	errRefusedDeal    = errors.New("the engine refused to deal the next round")
)

func (g *game) engineWait() wait {
	if g.holdingDraw {
		return wait{kind: waitDealt}
	}
	return waitOf(g.engine.Awaiting())
}

func (g *game) requireAct(seat tile.Seat, action play.Action) ([]play.Emitted, error) {
	next, events, refusal := g.engine.Act(seat, action)
	if refusal.OK {
		return nil, fmt.Errorf("session call refused: %s: %s", refusal.Value.Kind, refusal.Value.Code)
	}
	g.engine = next
	return events, nil
}

func (g *game) followEngine(events []play.Emitted, actor play.Option[tile.Seat]) error {
	err := g.applyUpdate(events, actor)
	if err != nil {
		return err
	}
	return g.playAIPlayers()
}

func (g *game) applyUpdate(events []play.Emitted, actor play.Option[tile.Seat]) error {
	awaiting := g.engineWait()
	previous, had := g.wait, g.hasWait
	g.wait, g.hasWait = awaiting, true
	opened := !had || opensNewWait(previous, awaiting, actor)

	var openings []messaging.Opening
	if opened {
		err := g.openWait(events, awaiting)
		if err != nil {
			return err
		}
		openings, err = g.openings(awaiting)
		if err != nil {
			return err
		}
	} else {
		for _, seat := range previous.seats {
			if !awaiting.awaits(seat) {
				g.stopTimerAt(seat)
			}
		}
	}

	err := g.broadcastEvents(events, openings)
	if err != nil {
		return err
	}
	if opened && g.lifecycle == lifecyclePlaying {
		g.startWaitTimers()
	}
	return nil
}

func (g *game) openWait(events []play.Emitted, awaiting wait) error {
	for _, p := range g.participants {
		p.timer.stop()
	}
	g.aiTurn.cancel()
	if holdsDeal(events) {
		for _, p := range g.participants {
			p.timer.resetBank()
		}
	}
	if awaiting.kind == waitRoundOver {
		err := g.openRoundOverPause(events)
		if err != nil {
			return err
		}
	}

	for _, p := range g.connected() {
		if g.owesDecision(p.seat) {
			p.decisionID++
		}
	}
	return nil
}

func (g *game) owesDecision(seat tile.Seat) bool {
	if g.pause != nil {
		return g.pause.owes(seat)
	}
	return g.wait.awaits(seat)
}

func holdsDeal(events []play.Emitted) bool {
	return slices.ContainsFunc(events, func(e play.Emitted) bool {
		_, dealt := e.Event.(play.RoundStarted)
		return dealt
	})
}

func (g *game) openRoundOverPause(events []play.Emitted) error {
	opened := pause{resultsShown: 1}
	for _, p := range g.connected() {
		opened.owing[p.seat.Index()] = true
	}
	if !opened.anyOwing() {
		return errNoConnected
	}
	for _, e := range events {
		if ended, ok := e.Event.(play.RoundEnded); ok {
			if ron, isRon := ended.Result.(play.Ron); isRon {
				opened.resultsShown = len(ron.Wins)
			}
		}
	}
	g.pause = &opened
	return nil
}

func (g *game) openings(awaiting wait) ([]messaging.Opening, error) {
	var openings []messaging.Opening
	for _, seat := range awaiting.seats {
		if g.isAISeat(seat) {
			continue
		}
		decision, ok := g.engine.Decision(seat)
		if !ok {
			return nil, errNoDecision
		}
		openings = append(openings, messaging.BuildOpening(decision))
	}
	return openings, nil
}

func (g *game) lazyTable() func() messaging.Table {
	var table messaging.Table
	computed := false
	return func() messaging.Table {
		if !computed {
			table = messaging.Table{Roster: g.roster, Record: g.engine.View(tile.Seats()[0]).Record}
			computed = true
		}
		return table
	}
}

func (g *game) broadcastEvents(events []play.Emitted, openings []messaging.Opening) error {
	table := g.lazyTable()
	err := g.sendEvents(events, openings, table)
	if err != nil {
		return err
	}
	if g.wait.kind != waitGameOver {
		return nil
	}

	result, ok := gameResult(events, table)
	if !ok {
		return errGameOverNoEnd
	}
	g.endGame(endCompleted, play.Some(result))
	return nil
}

func gameResult(events []play.Emitted, table func() messaging.Table) (store.Result, bool) {
	for _, e := range events {
		ended, ok := e.Event.(play.GameEnded)
		if !ok {
			continue
		}
		seats := tile.Seats()
		ordered := seats[:]
		slices.SortFunc(ordered, func(a, b tile.Seat) int {
			return ended.Standings.Placements[a.Index()] - ended.Standings.Placements[b.Index()]
		})
		result := store.Result{RoundsPlayed: int(table().Record.Header.RoundNumber) + 1}
		for _, s := range ordered {
			result.Placements = append(result.Placements, store.Placement{
				Seat:       s.Index(),
				Score:      ended.Standings.Scores[s.Index()],
				FinalScore: ended.Standings.Points[s.Index()],
			})
		}
		return result, true
	}
	return store.Result{}, false
}

func (g *game) sendEvents(events []play.Emitted, openings []messaging.Opening, table func() messaging.Table) error {
	if g.replay != nil {
		err := g.replay.collect(events, table)
		if err != nil {
			return err
		}
	}

	for _, placed := range messaging.PlaceOpenings(events, openings) {
		var err error
		switch item := placed.(type) {
		case messaging.Opening:
			err = g.sendOpening(item)
		case messaging.PlacedEvent:
			err = g.sendEvent(item.Emitted, table)
		}
		if err != nil {
			return err
		}
	}
	return nil
}

func (g *game) sendOpening(opening messaging.Opening) error {
	p := g.atSeat(opening.Seat)
	if p == nil || p.conn == nil {
		return nil
	}
	return send(p.conn, messaging.StampOpening(opening.Payload, p.decisionID, seconds(p.timer.bank), play.Option[float64]{}))
}

func (g *game) sendEvent(emitted play.Emitted, table func() messaging.Table) error {
	if started, ok := emitted.Event.(play.GameStarted); ok {
		return g.sendGameStarted(started)
	}

	payload, err := messaging.EventPayload(emitted.Event, table())
	if err != nil {
		return err
	}
	seat, single := emitted.To.Seat()
	if !single {
		return g.broadcastEvent(payload, emitted)
	}
	p := g.atSeat(seat)
	if p == nil {
		return nil
	}
	return g.sendEventTo(p, payload, emitted)
}

func (g *game) sendGameStarted(started play.GameStarted) error {
	payload, err := messaging.EventPayload(started, messaging.Table{Roster: g.roster})
	if err != nil {
		return err
	}
	for _, p := range g.connected() {
		stamped := messaging.StampViewerSeat(payload, p.seat)
		err = send(p.conn, messaging.StampTimerSettings(stamped, g.timerSettings(p)))
		if err != nil {
			return err
		}
	}
	return nil
}

func (g *game) broadcastEvent(payload wire.Map, emitted play.Emitted) error {
	if !g.opensPause(emitted) {
		return g.broadcast(payload)
	}
	for _, p := range g.connected() {
		err := g.sendEventTo(p, payload, emitted)
		if err != nil {
			return err
		}
	}
	return nil
}

func (g *game) sendEventTo(p *participant, payload wire.Map, emitted play.Emitted) error {
	if p.conn == nil {
		return nil
	}
	if g.opensPause(emitted) {
		payload = messaging.StampPause(payload, p.decisionID, seconds(g.pauseTimeout()))
	}
	return send(p.conn, payload)
}

func (g *game) opensPause(emitted play.Emitted) bool {
	if g.pause == nil {
		return false
	}
	if g.pause.startsGame {
		_, dealt := emitted.Event.(play.RoundStarted)
		seat, single := emitted.To.Seat()
		return dealt && single && g.pause.owes(seat)
	}
	_, ended := emitted.Event.(play.RoundEnded)
	return ended
}

func (g *game) broadcast(m wire.Map) error {
	connected := g.connected()
	if len(connected) == 0 {
		return nil
	}
	data, err := wire.Encode(m)
	if err != nil {
		return err
	}
	for _, p := range connected {
		p.conn.Send(data)
	}
	return nil
}

func (g *game) timerSettings(p *participant) messaging.TimerSettings {
	return messaging.TimerSettings{
		BaseTurn:            g.timing.BaseTurn.Seconds(),
		Bank:                p.timer.bank.Seconds(),
		MaxBank:             g.timing.InitialBank.Seconds(),
		RoundAdvanceTimeout: g.timing.RoundAdvance.Seconds(),
		GameStartConfirm:    g.timing.GameStartConfirm.Seconds(),
	}
}
