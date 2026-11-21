package main

import (
	"cmp"
	"errors"
	"fmt"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type seating struct {
	players []string
	absent  []int
}

func atTheTable() seating {
	return seating{players: []string{"Alice", "Bob", "Charlie", "Diana"}}
}

type scriptedGame struct {
	id        string
	game      engine.Game
	setup     engine.Setup
	roster    messaging.Roster
	log       *messaging.ReplayLog
	callEnds  []int
	ai        [tile.SeatCount]bool
	draws     map[tile.Seat]tile.TileID
	dealt     fillerDealers
	staged    []stagedDraw
	nextDraw  int
	firstDeal uint32
	err       error
}

func newScriptedGame(
	id string, seed engine.Seed, roster messaging.Roster, setup engine.Setup, absent []tile.Seat, staged []stagedDraw,
) *scriptedGame {
	g := &scriptedGame{
		id: id, setup: setup, roster: roster, log: messaging.NewReplayLog(seed, roster),
		ai: roster.AI, draws: map[tile.Seat]tile.TileID{}, dealt: fillerDealers{},
		staged: staged, firstDeal: setup.Start.Value.RoundNumber,
	}
	started, events, err := engine.NewGame(setup)
	if err != nil {
		g.fail(fmt.Errorf("start the game: %w", err))
		return g
	}
	g.game = started

	g.collect(events)
	for _, seat := range absent {
		g.ai[seat.Index()] = true
		g.log.AddSeatControl(seat, play.Some(wire.SeatControlAbsent))
	}
	g.endCall()
	g.begin()
	g.playAIPlayers()
	g.endCall()
	return g
}

func (g *scriptedGame) begin() {
	if g.err != nil {
		return
	}
	if _, dealt := g.game.Awaiting().(play.AwaitingDealt); !dealt {
		return
	}
	next, events, refusal := g.game.Begin()
	if refusal.OK {
		g.fail(fmt.Errorf("the dealer's first draw refused: %s: %s", refusal.Value.Kind, refusal.Value.Code))
		return
	}
	g.game = next
	g.collect(events)
}

func (g *scriptedGame) fail(err error) {
	if g.err == nil {
		g.err = fmt.Errorf("%s: %w", g.id, err)
	}
}

func (g *scriptedGame) seat(n int) (tile.Seat, bool) {
	seat, ok := tile.NewSeat(n)
	if !ok {
		g.fail(fmt.Errorf("no seat %d", n))
	}
	return seat, ok
}

func (g *scriptedGame) collect(events []play.Emitted) {
	if g.err != nil {
		return
	}
	table := func() messaging.Table {
		return messaging.Table{Roster: g.roster, Record: g.game.View(tile.Seats()[0]).Record}
	}
	err := g.log.Collect(events, table)
	if err != nil {
		g.fail(fmt.Errorf("record the events: %w", err))
		return
	}

	for _, e := range events {
		switch event := e.Event.(type) {
		case play.RoundStarted:
			g.dealt[event.Header.RoundNumber] = event.Header.Dealer
		case play.Drew:
			g.checkDraw(event)
			g.draws[event.Seat] = event.Tile
		case play.GameStarted, play.DrewNotice, play.Discarded, play.RiichiDeposited, play.FuritenChanged,
			play.Called, play.PaoAssigned, play.DoraRevealed, play.RoundEnded, play.GameEnded:
		}
	}
}

func (g *scriptedGame) checkDraw(drew play.Drew) {
	if g.game.View(drew.Seat).Record.Header.RoundNumber != g.firstDeal {
		return
	}
	index := slices.IndexFunc(g.staged, func(d stagedDraw) bool { return d.id == drew.Tile })
	if index < 0 {
		return
	}
	if index != g.nextDraw || drew.Seat != g.staged[index].seat {
		g.fail(fmt.Errorf("seat %d drew staged draw %d (staged for seat %d) as draw %d",
			drew.Seat.Index(), index, g.staged[index].seat.Index(), g.nextDraw))
		return
	}
	g.nextDraw++
}

func (g *scriptedGame) endCall() {
	g.callEnds = append(g.callEnds, len(g.log.Records()))
}

func (g *scriptedGame) step(seat tile.Seat, action play.Action) {
	g.apply(seat, action)
	g.playAIPlayers()
	g.endCall()
}

func (g *scriptedGame) apply(seat tile.Seat, action play.Action) {
	if g.err != nil {
		return
	}
	next, events, refusal := g.game.Act(seat, action)
	if refusal.OK {
		g.fail(fmt.Errorf("seat %d %+v refused: %s: %s",
			seat.Index(), action, refusal.Value.Kind, refusal.Value.Code))
		return
	}
	g.game = next
	delete(g.draws, seat)
	g.collect(events)
}

func (g *scriptedGame) playAIPlayers() {
	for g.err == nil {
		at := slices.IndexFunc(awaitedSeats(g.game.Awaiting()), func(s tile.Seat) bool { return g.ai[s.Index()] })
		if at < 0 {
			return
		}
		seat := awaitedSeats(g.game.Awaiting())[at]
		decision, ok := g.game.Decision(seat)
		if !ok {
			g.fail(fmt.Errorf("AI player's seat %d awaited with no decision", seat.Index()))
			return
		}
		g.apply(seat, decision.Default)
	}
}

func awaitedSeats(awaiting play.Awaiting) []tile.Seat {
	switch a := awaiting.(type) {
	case play.AwaitingTurn:
		return []tile.Seat{a.Seat}
	case play.AwaitingCall:
		return a.Seats
	case play.AwaitingDealt, play.AwaitingRoundOver, play.AwaitingGameOver:
	}
	return nil
}

func lowestSeat(seats []tile.Seat) tile.Seat {
	return slices.MinFunc(seats, func(a, b tile.Seat) int { return a.Index() - b.Index() })
}

func (g *scriptedGame) advanceRound() {
	if g.err != nil {
		return
	}
	next, events, refusal := g.game.DealNextRound()
	if refusal.OK {
		g.fail(fmt.Errorf("the next round's deal refused: %s: %s", refusal.Value.Kind, refusal.Value.Code))
		return
	}
	g.game = next
	g.collect(events)
	g.begin()
	g.playAIPlayers()
	g.endCall()
}

func (g *scriptedGame) recording() recording {
	return recording{records: g.log.Records(), callEnds: slices.Clone(g.callEnds), setup: g.setup}
}

type stagedGame struct {
	*scriptedGame
}

func openStagedGame(id string, staged stagedWall, seats seating, start play.Option[play.StartPosition],
	dealers fillerDealers,
) *stagedGame {
	dealer := tile.Seats()[0]
	if start.OK {
		dealer = start.Value.Dealer
	}
	if staged.dealer != dealer {
		failed := &scriptedGame{id: id}
		failed.fail(fmt.Errorf("a staged game's first round is dealt from seat %d, not %d",
			dealer.Index(), staged.dealer.Index()))
		return &stagedGame{failed}
	}

	seed := stagedSeed()
	setup, setupErr := stagedSetup(seed, []stagedWall{staged}, start, dealers)
	roster, playerSeats := session.SeatPlayers(id, seats.players, seed)
	var absent []tile.Seat
	var absentErr error
	for _, seat := range playerSeats {
		if slices.Contains(seats.absent, seat.Index()) {
			absent = append(absent, seat)
		}
	}
	if len(absent) != len(seats.absent) || len(absent) == len(playerSeats) {
		absentErr = fmt.Errorf("absent seats %v are not some of the players' %v", seats.absent, playerSeats)
	}
	if err := errors.Join(setupErr, absentErr); err != nil {
		failed := &scriptedGame{id: id}
		failed.fail(err)
		return &stagedGame{failed}
	}

	return &stagedGame{newScriptedGame(id, seed, roster, setup, absent, staged.draws)}
}

func (g *stagedGame) discard(seat int, id tile.TileID) {
	g.act(seat, play.DiscardAction(id))
}

func (g *stagedGame) tsumogiri(seat int) {
	drawn, ok := g.drawn(seat)
	if ok {
		g.discard(seat, drawn)
	}
}

func (g *stagedGame) riichi(seat int) {
	drawn, ok := g.drawn(seat)
	if ok {
		g.riichiOn(seat, drawn)
	}
}

func (g *stagedGame) riichiOn(seat int, id tile.TileID) {
	g.act(seat, play.RiichiAction(id))
}

func (g *stagedGame) pon(seat int) {
	s, ok := g.seat(seat)
	if !ok {
		return
	}
	g.passCalls(s)
	pons := slices.DeleteFunc(g.game.LegalActions(s), func(a play.Action) bool { return a.Kind() != play.ActionPon })
	if len(pons) != 1 {
		g.fail(fmt.Errorf("seat %d is offered %d pons, not one", seat, len(pons)))
		return
	}
	g.step(s, pons[0])
}

func (g *stagedGame) kan(seat int, id tile.TileID, kind play.KanKind) {
	g.act(seat, play.KanAction(kind, id))
}

func (g *stagedGame) tsumo(seat int) {
	g.act(seat, play.TsumoAction())
}

func (g *stagedGame) kyuushu(seat int) {
	g.act(seat, play.KyuushuAction())
}

func (g *stagedGame) ron(seats ...int) {
	declaring := make([]tile.Seat, 0, len(seats))
	for _, n := range seats {
		s, ok := g.seat(n)
		if !ok {
			return
		}
		declaring = append(declaring, s)
	}
	g.passCalls(declaring...)
	for _, s := range declaring {
		g.step(s, play.RonAction())
	}
}

func (g *stagedGame) leave(seat int) {
	s, ok := g.seat(seat)
	if !ok || g.err != nil {
		return
	}
	if g.ai[s.Index()] {
		g.fail(fmt.Errorf("seat %d was replaced with an AI player twice", seat))
		return
	}
	g.ai[s.Index()] = true
	g.log.AddSeatControl(s, play.Some(wire.SeatControlLeft))
	g.playAIPlayers()
	g.endCall()
}

func (g *stagedGame) restoreHuman(seat int) {
	s, ok := g.seat(seat)
	if !ok || g.err != nil {
		return
	}
	if !g.ai[s.Index()] {
		g.fail(fmt.Errorf("seat %d was restored without an AI player in it", seat))
		return
	}
	g.ai[s.Index()] = false
	g.log.AddSeatControl(s, play.Option[wire.SeatControlReason]{})
	g.endCall()
}

func (g *stagedGame) tsumogiriUntil(seat int) {
	s, ok := g.seat(seat)
	if ok {
		g.tsumogiriTo(play.Some(s))
	}
}

func (g *stagedGame) tsumogiriToRoundEnd() {
	g.tsumogiriTo(play.Option[tile.Seat]{})
}

func (g *stagedGame) tsumogiriTo(seat play.Option[tile.Seat]) {
	for g.err == nil {
		g.passCalls()
		turn, isTurn := g.game.Awaiting().(play.AwaitingTurn)
		switch {
		case g.err != nil || (!isTurn && !seat.OK):
			return
		case !isTurn:
			g.fail(fmt.Errorf("the round ended before seat %d's turn", seat.Value.Index()))
			return
		case seat.OK && turn.Seat == seat.Value:
			return
		case slices.Contains(g.game.LegalActions(turn.Seat), play.TsumoAction()):
			g.fail(fmt.Errorf("seat %d was offered tsumo while discarding draws", turn.Seat.Index()))
			return
		}
		g.tsumogiri(turn.Seat.Index())
	}
}

func (g *stagedGame) confirmRound() {
	g.advanceRound()
}

func (g *stagedGame) act(seat int, action play.Action) {
	s, ok := g.seat(seat)
	if !ok {
		return
	}
	if action.AnswersCall() && action.Kind() != play.ActionPass {
		g.passCalls(s)
	} else {
		g.passCalls()
	}
	g.step(s, action)
}

func (g *stagedGame) passCalls(exclude ...tile.Seat) {
	for g.err == nil {
		call, open := g.game.Awaiting().(play.AwaitingCall)
		if !open {
			return
		}
		answering := slices.DeleteFunc(slices.Clone(call.Seats), func(s tile.Seat) bool {
			return slices.Contains(exclude, s)
		})
		if len(answering) == 0 {
			return
		}
		seat := lowestSeat(answering)
		if slices.Contains(g.game.LegalActions(seat), play.RonAction()) {
			g.fail(fmt.Errorf("seat %d was offered ron; pass it or call it", seat.Index()))
			return
		}
		g.step(seat, play.PassAction())
	}
}

func (g *stagedGame) drawn(seat int) (tile.TileID, bool) {
	s, ok := g.seat(seat)
	if !ok {
		return tile.TileID{}, false
	}
	drawn, ok := g.draws[s]
	if !ok {
		g.fail(fmt.Errorf("seat %d has no drawn tile", seat))
	}
	return drawn, ok
}

func (g *stagedGame) replay(want outcome) (recording, error) {
	if g.err == nil && g.nextDraw != len(g.staged) {
		g.fail(fmt.Errorf("draw %d and later were staged but not drawn", g.nextDraw))
	}
	if g.err != nil {
		return recording{}, g.err
	}

	played := g.recording()
	err := requireOutcome(g.id, played, want)
	if err != nil {
		return recording{}, err
	}
	g.passCalls()
	if _, over := g.game.Awaiting().(play.AwaitingRoundOver); over {
		g.confirmRound()
	}
	if g.err != nil {
		return recording{}, g.err
	}
	return played, requireReproduces(g.id, played, g.game)
}

func playPolicyGame(
	id string, seed engine.Seed, roster messaging.Roster, choose policy, want outcome,
) (recording, error) {
	g := newScriptedGame(id, seed, roster, engine.Setup{Walls: play.Seeded{Seed: seed}}, nil, nil)
	for g.err == nil {
		switch awaiting := g.game.Awaiting().(type) {
		case play.AwaitingGameOver:
			played := g.recording()
			return played, errors.Join(requireOutcome(id, played, want), requireReproduces(id, played, g.game))
		case play.AwaitingRoundOver:
			g.advanceRound()
		case play.AwaitingDealt:
			g.begin()
		case play.AwaitingTurn, play.AwaitingCall:
			seat := lowestSeat(awaitedSeats(awaiting))
			action, err := choose(g.game, seat, g.draws[seat])
			if err != nil {
				g.fail(err)
				break
			}
			g.step(seat, action)
		}
	}
	return recording{}, g.err
}

type policy func(game engine.Game, seat tile.Seat, drawn tile.TileID) (play.Action, error)

func defaultPolicy(game engine.Game, seat tile.Seat, _ tile.TileID) (play.Action, error) {
	action, ok := game.DefaultAction(seat)
	if !ok {
		return play.Action{}, fmt.Errorf("seat %d awaited with no default action", seat.Index())
	}
	return action, nil
}

func eagerPolicy(game engine.Game, seat tile.Seat, drawn tile.TileID) (play.Action, error) {
	legal := game.LegalActions(seat)
	switch _, isCall := game.Awaiting().(play.AwaitingCall); {
	case isCall && slices.Contains(legal, play.RonAction()):
		return play.RonAction(), nil
	case isCall:
		return play.PassAction(), nil
	case slices.Contains(legal, play.TsumoAction()):
		return play.TsumoAction(), nil
	}
	discard, err := closestToReadyDiscard(game.View(seat).Record.Hand, drawn)
	return play.DiscardAction(discard), err
}

type discardRank struct {
	shanten int
	drawn   bool
	id      tile.TileID
}

func closestToReadyDiscard(hand []tile.TileID, drawn tile.TileID) (tile.TileID, error) {
	ranks := make([]discardRank, 0, len(hand))
	for i, id := range hand {
		rest, err := tile.KindCounts(slices.Delete(slices.Clone(hand), i, i+1))
		if err != nil {
			return tile.TileID{}, err
		}
		shanten, err := engine.Shanten(rest)
		if err != nil {
			return tile.TileID{}, err
		}
		ranks = append(ranks, discardRank{shanten: shanten, drawn: id == drawn, id: id})
	}
	if len(ranks) == 0 {
		return tile.TileID{}, errors.New("an empty hand has no discard")
	}
	return slices.MinFunc(ranks, compareDiscardRanks).id, nil
}

func compareDiscardRanks(a, b discardRank) int {
	return cmp.Or(cmp.Compare(a.shanten, b.shanten), cmp.Compare(drawnRank(b), drawnRank(a)), b.id.Compare(a.id))
}

func drawnRank(r discardRank) int {
	if r.drawn {
		return 1
	}
	return 0
}
