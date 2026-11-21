// Package game plays a game of riichi mahjong under the engine's fixed rules: its setup, its
// phases and the calls that move it, the position each round is dealt at, how a round's end counts
// the honba and passes the deal, the rule that ends the game and its final standings. A game is a
// hanchan: East and South, then the West extension, played until a seat reaches the winning
// threshold or the last West round ends.
//
// A Game is a value. Every method that moves it returns the new game and leaves its receiver as it
// was, so a caller may keep or branch from any state; a refused action returns the receiver
// itself.
package game

import (
	"math"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/round"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	tablePoints = rules.StartingScore * tile.SeatCount
	scoreStep   = 100
)

type walls struct {
	seed  play.Option[rng.Seed]
	fixed []wall.Wall
}

func (w *walls) wallFor(p position) (wall.Wall, bool) {
	if w.seed.OK {
		return wall.FromSeed(w.seed.Value, p.roundNumber, p.dealer), true
	}
	if len(w.fixed) == 0 {
		return wall.Wall{}, false
	}

	next := w.fixed[0]
	w.fixed = w.fixed[1:]
	return next, true
}

// Game is the full state of a game. Its zero value is no game; build one with New.
type Game struct {
	phase           play.Phase
	header          play.RoundHeader
	points          round.Points
	round           round.Round
	history         []play.FinishedRound
	firstDealer     tile.Seat
	firstDealerDice [2]tile.Dice
	uniqueDealers   int
	walls           walls
	next            play.Option[position]
	standings       play.Option[play.Standings]
	drawPending     bool
}

// New sets a game up from its walls and an optional start position and deals its first round. It
// returns the game in play.PhasePlaying, awaiting play.AwaitingDealt, and its first events:
// GameStarted, then one RoundStarted per seat; Begin makes the dealer's first draw. A Fixed source
// deals seat 0 first with every throw (1, 1).
//
// The errors, checked in this order: the start position's StartInNorthError,
// StartScoreOffHundredsError, StartScoreBelowTobiError, NegativeStartCountError and
// StartPointsOffTotalError; an InvalidWallError for a fixed wall that repeats a tile; a
// NoFixedWallError for an empty Fixed list or a nil source.
func New(source play.WallSource, start play.Option[play.StartPosition]) (Game, []play.Emitted, error) {
	g := Game{firstDealerDice: [2]tile.Dice{{First: 1, Second: 1}, {First: 1, Second: 1}}}
	var fixedWalls [][tile.TileIDCount]tile.TileID
	switch s := source.(type) {
	case play.Seeded:
		seed := rng.Seed(s.Seed)
		dealer, first, second := rng.FirstDealer(seed)
		g.firstDealer, g.firstDealerDice, g.walls.seed = dealer, [2]tile.Dice{first, second}, play.Some(seed)
	case play.Fixed:
		fixedWalls = s.Walls
	}
	if start.OK {
		if err := checkStart(start.Value); err != nil {
			return Game{}, nil, err
		}
	}

	for _, tiles := range fixedWalls {
		w, err := wall.FromTiles(tiles)
		if err != nil {
			return Game{}, nil, InvalidWallError{Err: err}
		}
		g.walls.fixed = append(g.walls.fixed, w)
	}

	at := start.Value
	if !start.OK {
		at = play.StartPosition{Scores: [tile.SeatCount]int{
			rules.StartingScore, rules.StartingScore, rules.StartingScore, rules.StartingScore,
		}, Dealer: g.firstDealer}
	}
	p := position{
		roundNumber:   at.RoundNumber,
		dealer:        at.Dealer,
		wind:          at.Wind,
		uniqueDealers: uniqueDealersAt(at.Wind, at.Dealer.DistanceFrom(g.firstDealer)+1),
		honba:         at.Honba,
	}
	w, ok := g.walls.wallFor(p)
	if !ok {
		return Game{}, nil, NoFixedWallError{}
	}

	g.points = round.NewPoints(at.Scores, at.RiichiSticks)
	g.deal(p, w)
	events := []play.Emitted{toAll(play.GameStarted{FirstDealer: g.firstDealer, Dice: g.firstDealerDice})}
	return g, append(events, g.roundStartedEvents()...), nil
}

func checkStart(start play.StartPosition) error {
	if start.Wind >= tile.North {
		return StartInNorthError{}
	}

	for _, seat := range tile.Seats() {
		score := start.Scores[seat.Index()]
		if score%scoreStep != 0 {
			return StartScoreOffHundredsError{Seat: seat}
		}
		if rules.Tobi && score < rules.TobiThreshold {
			return StartScoreBelowTobiError{Seat: seat}
		}
	}
	if start.Honba < 0 || start.RiichiSticks < 0 {
		return NegativeStartCountError{}
	}

	found := saturatingMul(start.RiichiSticks, rules.RiichiStickValue)
	for _, score := range start.Scores {
		found = saturatingAdd(found, score)
	}
	if found != tablePoints {
		return StartPointsOffTotalError{Found: found, Expected: tablePoints}
	}
	return nil
}

func saturatingAdd(a, b int) int {
	if b > math.MaxInt-a {
		return math.MaxInt
	}
	return a + b
}

func saturatingMul(a, b int) int {
	if a > math.MaxInt/b {
		return math.MaxInt
	}
	return a * b
}

func uniqueDealersAt(wind tile.Wind, roundInWind int) int {
	return int(wind)*dealersPerWind + roundInWind
}

func (g *Game) deal(p position, w wall.Wall) {
	g.header = play.RoundHeader{
		RoundNumber:  p.roundNumber,
		Wind:         p.wind,
		RoundInWind:  p.dealer.DistanceFrom(g.firstDealer) + 1,
		Dealer:       p.dealer,
		Honba:        p.honba,
		RiichiSticks: g.points.RiichiSticks(),
		Dice:         w.Dice(),
	}
	g.uniqueDealers = p.uniqueDealers
	g.round = round.Deal(w, p.dealer, p.wind)
	g.next = play.Option[position]{}
	g.phase = play.PhasePlaying
	g.drawPending = true
}

func (g *Game) roundStartedEvents() []play.Emitted {
	w := g.round.Wall()
	events := make([]play.Emitted, 0, tile.SeatCount)
	for _, seat := range tile.Seats() {
		events = append(events, toSeat(seat, play.RoundStarted{
			Seat:           seat,
			Header:         g.header,
			Scores:         g.points.Scores(),
			Hand:           g.round.Hand(seat),
			DoraIndicators: w.DoraIndicators(),
			LiveTiles:      w.LiveCount(),
		}))
	}
	return events
}

// DealNextRound deals the round that follows the one just over: play.PhasePlaying, awaiting
// play.AwaitingDealt, and one RoundStarted per seat; Begin makes its dealer's first draw. Once
// every fixed wall has been dealt it ends the game instead with play.EndFixedWallsDealt:
// play.PhaseGameOver and a GameEnded. Outside play.PhaseRoundOver it is refused as not awaited.
func (g Game) DealNextRound() (Game, []play.Emitted, play.Option[play.Refusal]) {
	if !g.next.OK {
		return g, nil, notAwaited(play.CodeWrongPhase)
	}

	next := g
	w, ok := next.walls.wallFor(g.next.Value)
	if !ok {
		ended := next.endGame(play.EndFixedWallsDealt)
		return next, []play.Emitted{ended}, play.Option[play.Refusal]{}
	}

	next.deal(g.next.Value, w)
	return next, next.roundStartedEvents(), play.Option[play.Refusal]{}
}

// Begin makes the dealer's first draw of the round just dealt and returns its events. Unless the
// game awaits play.AwaitingDealt it is refused as not awaited.
func (g Game) Begin() (Game, []play.Emitted, play.Option[play.Refusal]) {
	if !g.drawPending {
		return g, nil, notAwaited(play.CodeWrongPhase)
	}

	next := g
	next.drawPending = false
	events := next.round.Begin()
	return next, events, play.Option[play.Refusal]{}
}

// Awaiting returns what the game waits for now.
func (g Game) Awaiting() play.Awaiting {
	switch g.phase {
	case play.PhaseRoundOver:
		return play.AwaitingRoundOver{}
	case play.PhaseGameOver:
		return play.AwaitingGameOver{}
	case play.PhasePlaying:
	}
	if g.drawPending {
		return play.AwaitingDealt{}
	}

	if prompt := g.round.Prompt(); prompt.OK {
		return play.AwaitingCall{Seats: prompt.Value.Pending()}
	}
	return play.AwaitingTurn{Seat: g.round.Current()}
}

func (g Game) isTurnOf(seat tile.Seat) bool {
	turn, ok := g.Awaiting().(play.AwaitingTurn)
	return ok && turn.Seat == seat
}

func (g Game) isCallFor(seat tile.Seat) bool {
	prompt := g.round.Prompt()
	return g.phase == play.PhasePlaying && prompt.OK && prompt.Value.IsPending(seat)
}

// LegalActions returns every action seat may take now, none for a seat that is not awaited. On a
// turn the discards come first in hand order (in riichi only the drawn tile, right after a call
// none of a kind kuikae forbids), then the riichi discards, tsumo, one closed kan per kind, one
// added kan per pon and kyuushu; on a call prompt ron, open kan, one pon per look, one chi per
// shape, then pass.
func (g Game) LegalActions(seat tile.Seat) []play.Action {
	if g.isCallFor(seat) {
		return g.round.Prompt().Value.Offers(seat)
	}
	if !g.isTurnOf(seat) {
		return nil
	}
	return g.round.TurnActions(seat, g.points.Score(seat))
}

// DefaultAction returns the action a timeout plays for seat: on a turn the drawn tile when it is
// a legal discard, else the last legal discard; on a call prompt pass. False for a seat that is not
// awaited.
func (g Game) DefaultAction(seat tile.Seat) (play.Action, bool) {
	if g.isCallFor(seat) {
		return play.PassAction(), true
	}
	return g.turnDefault(g.LegalActions(seat))
}

func (g Game) turnDefault(legal []play.Action) (play.Action, bool) {
	if drawn := g.round.Drawn(); drawn.OK && slices.Contains(legal, play.DiscardAction(drawn.Value)) {
		return play.DiscardAction(drawn.Value), true
	}
	for _, action := range slices.Backward(legal) {
		if action.Kind() == play.ActionDiscard {
			return action, true
		}
	}
	return play.Action{}, false
}

// Decision returns the prompt of seat; false for a seat that is not awaited.
func (g Game) Decision(seat tile.Seat) (play.Decision, bool) {
	legal := g.LegalActions(seat)
	fallback, ok := play.PassAction(), true
	if !g.isCallFor(seat) {
		fallback, ok = g.turnDefault(legal)
	}
	if !ok {
		return play.Decision{}, false
	}
	return play.Decision{Seat: seat, Context: g.decisionContext(), Legal: legal, Default: fallback}, true
}

func (g Game) decisionContext() play.DecisionContext {
	if prompt := g.round.Prompt(); prompt.OK {
		p := prompt.Value
		return play.Call{
			Tile:   p.Tile(),
			From:   p.From(),
			Source: p.Source(),
			Houtei: offer.IsHoutei(g.round.LiveTiles(), p.Source()),
		}
	}
	if drawn := g.round.Drawn(); drawn.OK {
		return play.TurnAfterDraw{
			Drawn:   drawn.Value,
			Rinshan: g.round.Rinshan(),
			Haitei:  offer.IsHaitei(g.round.LiveTiles(), g.round.Rinshan()),
		}
	}
	return play.TurnAfterCall{Kuikae: g.round.Kuikae()}
}

// Act applies one answer of seat and returns the game after it and the events it caused, each
// furiten change it brought last. A refusal returns the receiver unchanged and no events: not
// awaited outside a round in play or before its dealer's first draw, from a seat not awaited, for
// a turn action while a call prompt is open and for a call answer outside one; not offered for a
// tile the seat does not hold or an action it was not offered, a kan among them; rule for a riichi
// discard that breaks tenpai, a discard in riichi other than the drawn tile and a discard kuikae
// forbids.
func (g Game) Act(seat tile.Seat, action play.Action) (Game, []play.Emitted, play.Option[play.Refusal]) {
	if g.phase != play.PhasePlaying || g.drawPending {
		return g, nil, notAwaited(play.CodeWrongPhase)
	}
	if !action.AnswersCall() && !g.isTurnOf(seat) {
		return g, nil, notAwaited(play.CodeSeatNotAwaited)
	}

	next := g
	var t round.Transition
	var refusal play.Option[play.Refusal]
	if action.AnswersCall() {
		t, refusal = next.round.AnswerCall(seat, action, g.header.Honba, &next.points)
	} else {
		t, refusal = next.turnAction(seat, action)
	}
	if refusal.OK {
		return g, nil, refusal
	}

	if t.Ended != nil {
		finished := next.finishRound(t.Ended)
		return next, append(t.Events, finished...), play.Option[play.Refusal]{}
	}
	furiten := next.round.ReportFuriten()
	return next, append(t.Events, furiten...), play.Option[play.Refusal]{}
}

func (g *Game) turnAction(seat tile.Seat, action play.Action) (round.Transition, play.Option[play.Refusal]) {
	id, _ := action.Tile()
	kan, _ := action.Kan()
	switch action.Kind() {
	case play.ActionDiscard:
		return g.round.Discard(seat, id, &g.points)
	case play.ActionRiichi:
		return g.round.DeclareRiichi(seat, id, &g.points)
	case play.ActionTsumo:
		return g.round.Tsumo(seat, g.header.Honba, g.points)
	case play.ActionKyuushu:
		return g.round.Kyuushu(seat)
	case play.ActionKan:
		return g.round.DeclareKan(seat, kan, id)
	case play.ActionRon, play.ActionPass, play.ActionPon, play.ActionChi:
	}
	return round.Transition{}, play.Some(play.Refusal{Kind: play.RefusalNotOffered, Code: play.CodeNotOffered})
}

func (g *Game) finishRound(result play.RoundResult) []play.Emitted {
	g.points.ApplyChanges(result.TotalScoreChanges())
	switch result.(type) {
	case play.Tsumo, play.Ron:
		g.points.ClearSticks()
	case play.ExhaustiveDraw, play.Abortive:
	}

	ended := position{
		roundNumber:   g.header.RoundNumber,
		dealer:        g.header.Dealer,
		wind:          g.header.Wind,
		uniqueDealers: g.uniqueDealers,
		honba:         g.header.Honba,
	}
	next := ended.after(result)
	cause, ends := gameEndCause(ended, next, result, g.points.Scores(), g.firstDealer)
	var riichiSeats []tile.Seat
	for _, seat := range tile.Seats() {
		if g.round.InRiichi(seat) {
			riichiSeats = append(riichiSeats, seat)
		}
	}
	g.history = append(slices.Clip(g.history), play.FinishedRound{
		Header:      g.header,
		Result:      result,
		RiichiSeats: riichiSeats,
	})

	events := []play.Emitted{toAll(play.RoundEnded{
		Result:       result,
		Scores:       g.points.Scores(),
		RiichiSticks: g.points.RiichiSticks(),
	})}
	if !ends {
		g.next = play.Some(next)
		g.phase = play.PhaseRoundOver
		return events
	}
	return append(events, g.endGame(cause))
}

func (g *Game) endGame(cause play.GameEndCause) play.Emitted {
	standings := finalStandings(g.points.Scores(), g.points.RiichiSticks(), g.firstDealer, cause)
	g.points.SetFinal(standings.Scores)
	g.standings = play.Some(standings)
	g.next = play.Option[position]{}
	g.phase = play.PhaseGameOver
	return toAll(play.GameEnded{Standings: standings})
}

// SeatView returns what seat may see of the game now: its own hand, drawn tile, furiten and
// decision, every seat's public table, the round's header (the ended round's while the game waits
// on its end or is over, beside its result) and every finished round. It holds no other seat's
// concealed tiles, decision, furiten or pending answer, and shares no slice with the game.
func (g Game) SeatView(seat tile.Seat) play.SeatView {
	decision, awaited := g.Decision(seat)
	var drawn play.Option[tile.TileID]
	if turn, afterDraw := decision.Context.(play.TurnAfterDraw); afterDraw {
		drawn = play.Some(turn.Drawn)
	}
	var result play.RoundResult
	if g.phase != play.PhasePlaying && len(g.history) > 0 {
		result = g.history[len(g.history)-1].Result
	}

	var players [tile.SeatCount]play.PublicSeat
	for _, player := range tile.Seats() {
		players[player.Index()] = play.PublicSeat{
			Seat:        player,
			Score:       g.points.Score(player),
			ClosedTiles: len(g.round.Hand(player)),
			River:       g.round.River(player),
			Melds:       g.round.Melds(player),
			Riichi:      g.round.Riichi(player),
			Pao:         g.round.Pao(player),
		}
	}
	seen := play.SeatRecord{
		Seat:            seat,
		Hand:            g.round.Hand(seat),
		Drawn:           drawn,
		Furiten:         g.round.ShownFuriten(seat),
		Players:         players,
		DoraIndicators:  g.round.Wall().DoraIndicators(),
		LiveTiles:       g.round.LiveTiles(),
		RiichiSticks:    g.points.RiichiSticks(),
		Current:         g.round.Current(),
		LatestDiscard:   g.round.LatestDiscard(),
		Header:          g.header,
		Result:          result,
		Phase:           g.phase,
		FirstDealer:     g.firstDealer,
		FirstDealerDice: g.firstDealerDice,
		History:         g.history,
	}
	return play.SeatView{
		Record:   record.Clone(seen),
		Decision: play.Option[play.Decision]{Value: decision, OK: awaited},
	}
}

// CheckOwnership checks that each of the 136 tiles is in exactly one place: the wall, a hand, a
// meld or a river, a called tile counting in its discarder's river and not in the meld. The error
// is a wall.MissingTileError or wall.TileInTwoPlacesError naming the lowest tile id at fault.
func (g Game) CheckOwnership() error {
	return g.round.CheckOwnership()
}

// CheckInvariants checks what every step of a game keeps: each tile in one place (see
// CheckOwnership), the scores and riichi sticks adding up to the points the game started with,
// and once the game is over final scores that add up to them too, points that sum to 0 and the
// places 1 to 4. The first broken one is returned, in that order: an OwnershipError,
// TablePointsError, FinalScoresError, FinalPointsError or PlacementsError.
func (g Game) CheckInvariants() error {
	if err := g.CheckOwnership(); err != nil {
		return OwnershipError{Err: err}
	}
	if found := g.points.Total(); found != tablePoints {
		return TablePointsError{Found: found, Expected: tablePoints}
	}
	if !g.standings.OK {
		return nil
	}

	standings := g.standings.Value
	scores, points := 0, 0
	for seat := range standings.Scores {
		scores += standings.Scores[seat]
		points += standings.Points[seat]
	}
	placements := standings.Placements
	slices.Sort(placements[:])
	switch {
	case scores != tablePoints:
		return FinalScoresError{Found: scores, Expected: tablePoints}
	case points != 0:
		return FinalPointsError{Points: points}
	case placements != [tile.SeatCount]int{1, 2, 3, 4}:
		return PlacementsError{Placements: standings.Placements}
	default:
		return nil
	}
}

// Phase returns the phase of the game.
func (g Game) Phase() play.Phase {
	return g.phase
}

// Header returns the header of the current round; after a round ends, still that round's.
func (g Game) Header() play.RoundHeader {
	return g.header
}

// Scores returns the scores by seat; once the game is over, the final ones.
func (g Game) Scores() [tile.SeatCount]int {
	return g.points.Scores()
}

// RiichiSticks returns the riichi sticks on the table; once the game is over, 0.
func (g Game) RiichiSticks() int {
	return g.points.RiichiSticks()
}

// Standings returns the final standings, once the game is over.
func (g Game) Standings() play.Option[play.Standings] {
	return g.standings
}

// Hand returns a copy of the concealed tiles of seat, in hand order: the dealt tiles sorted by id,
// then each draw at the end.
func (g Game) Hand(seat tile.Seat) []tile.TileID {
	return g.round.Hand(seat)
}

// LiveTiles returns the tiles left in the live wall.
func (g Game) LiveTiles() int {
	return g.round.LiveTiles()
}

// History returns a copy of the finished rounds, in play order.
func (g Game) History() []play.FinishedRound {
	return slices.Clone(g.history)
}

func toAll(event play.Event) play.Emitted {
	return play.Emitted{To: play.ToAll(), Event: event}
}

func toSeat(seat tile.Seat, event play.Event) play.Emitted {
	return play.Emitted{To: play.ToSeat(seat), Event: event}
}

func notAwaited(code play.RefusalCode) play.Option[play.Refusal] {
	return play.Some(play.Refusal{Kind: play.RefusalNotAwaited, Code: code})
}
