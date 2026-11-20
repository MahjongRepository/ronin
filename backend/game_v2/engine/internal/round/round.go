// Package round plays one round: the wall, the hands, melds and rivers, riichi and furiten, the
// draws, discards, calls and kans that move them, the call prompt on a discard or a kan, how the
// round ends, and the table's points ledger.
//
// A Round is a value, changed only through the copy its methods are called on: hands and melds
// are fixed-size arrays sized from their proven bounds (14 tiles, 4 melds), and every slice it
// holds is replaced, never written in place, so a copy taken before a change keeps its state. A
// method that refuses an action changes nothing.
//
// Ported from mahjong-rs's mahjong-game at commit 0d8733f: its round, round/settle, calls and
// points modules.
package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const drawnHandRemainder = 2

// Transition is the events of one step of a round, and the round's result when the step ended it,
// nil while the round goes on.
type Transition struct {
	Events []play.Emitted
	Ended  play.RoundResult
}

func playing(events []play.Emitted) Transition {
	return Transition{Events: events}
}

func ended(events []play.Emitted, result play.RoundResult) Transition {
	return Transition{Events: events, Ended: result}
}

// Round is the state of one round in play. Rivers hold every discard of each seat, the called
// ones included; a hand holds the dealt tiles sorted, then each draw at the end.
type Round struct {
	wall              wall.Wall
	dealer            tile.Seat
	roundWind         tile.Wind
	hands             [tile.SeatCount]handTiles
	rivers            [tile.SeatCount][]play.RiverTile
	latestDiscard     play.Option[tile.Seat]
	melds             [tile.SeatCount]seatMelds
	kuikae            []tile.Kind
	pao               [tile.SeatCount]play.Option[tile.Seat]
	current           tile.Seat
	drawn             play.Option[tile.TileID]
	rinshan           bool
	riichi            [tile.SeatCount]play.Option[play.Riichi]
	furiten           [tile.SeatCount]offer.Furiten
	undepositedRiichi play.Option[tile.Seat]
	prompt            play.Option[CallPrompt]
}

// Deal deals the starting hands of a fresh wall from dealer, in a round of roundWind. The dealer
// is on turn and has not drawn yet.
func Deal(w wall.Wall, dealer tile.Seat, roundWind tile.Wind) Round {
	dealt := w.Deal(dealer)
	r := Round{wall: w, dealer: dealer, roundWind: roundWind, current: dealer}
	for i, held := range dealt {
		r.hands[i] = newHand(held)
	}
	return r
}

// Wall returns the round's wall.
func (r *Round) Wall() wall.Wall {
	return r.wall
}

// Hand returns a copy of seat's concealed tiles, in hand order.
func (r *Round) Hand(seat tile.Seat) []tile.TileID {
	return r.hands[seat.Index()].ids()
}

// Current returns the seat whose turn it is or was last.
func (r *Round) Current() tile.Seat {
	return r.current
}

// Drawn returns the tile the current seat drew, until its discard, call or kan.
func (r *Round) Drawn() play.Option[tile.TileID] {
	return r.drawn
}

// River returns a copy of seat's discards, the called ones included.
func (r *Round) River(seat tile.Seat) []play.RiverTile {
	return slices.Clone(r.rivers[seat.Index()])
}

// Melds returns a copy of seat's melds, in call order.
func (r *Round) Melds(seat tile.Seat) []play.MeldView {
	return slices.Clone(r.melds[seat.Index()].view())
}

// Kuikae returns a copy of the kinds the seat on its turn right after its own call may not
// discard.
func (r *Round) Kuikae() []tile.Kind {
	return slices.Clone(r.kuikae)
}

// Rinshan reports whether the drawn tile came from the dead wall.
func (r *Round) Rinshan() bool {
	return r.rinshan
}

// InRiichi reports whether seat's riichi is in effect.
func (r *Round) InRiichi(seat tile.Seat) bool {
	return r.riichi[seat.Index()].OK
}

// Riichi returns seat's riichi once in effect, the riichi discard having passed every ron: whether
// it is double and whether its ippatsu still stands.
func (r *Round) Riichi(seat tile.Seat) play.Option[play.Riichi] {
	return r.riichi[seat.Index()]
}

// Pao returns the seat liable for seat's daisangen or daisuushii, having fed the set that
// completed it.
func (r *Round) Pao(seat tile.Seat) play.Option[tile.Seat] {
	return r.pao[seat.Index()]
}

// LatestDiscard returns the seat whose discard is the table's last action: absent before the
// first discard, once a meld claimed it and once the next seat drew.
func (r *Round) LatestDiscard() play.Option[tile.Seat] {
	return r.latestDiscard
}

// ShownFuriten returns the furiten seat was last shown.
func (r *Round) ShownFuriten(seat tile.Seat) bool {
	return r.furiten[seat.Index()].Shown
}

// LiveTiles returns the tiles left in the live wall.
func (r *Round) LiveTiles() int {
	return r.wall.LiveCount()
}

// Prompt returns the open call prompt.
func (r *Round) Prompt() play.Option[CallPrompt] {
	return r.prompt
}

func (r *Round) hand(seat tile.Seat) []tile.TileID {
	return r.hands[seat.Index()].view()
}

func (r *Round) seatMelds(seat tile.Seat) []play.MeldView {
	return r.melds[seat.Index()].view()
}

func (r *Round) meldsBySeat() [tile.SeatCount][]play.MeldView {
	var melds [tile.SeatCount][]play.MeldView
	for i := range melds {
		melds[i] = r.melds[i].view()
	}
	return melds
}

func (r *Round) hasAnyCall() bool {
	for _, melds := range r.melds {
		if melds.count > 0 {
			return true
		}
	}
	return false
}

func (r *Round) meldedTiles(seat tile.Seat) []tile.TileID {
	var tiles []tile.TileID
	for _, view := range r.seatMelds(seat) {
		tiles = append(tiles, view.Tiles...)
	}
	return tiles
}

// Begin makes the dealer's first draw and returns its events; a fresh wall always has it.
func (r *Round) Begin() []play.Emitted {
	return r.drawTurn(r.dealer, nil).Events
}

// Discard discards id from seat's hand, then settles the discard.
func (r *Round) Discard(seat tile.Seat, id tile.TileID, points *Points) (Transition, play.Option[play.Refusal]) {
	position, refusal := r.checkDiscard(seat, id)
	if refusal.OK {
		return Transition{}, refusal
	}

	tsumogiri := r.moveToRiver(seat, position, id)
	return r.settleDiscard(seat, id, tsumogiri, points), play.Option[play.Refusal]{}
}

// DeclareRiichi declares riichi on the discard of id, then settles the discard; the deposit waits
// for its ron window to pass.
func (r *Round) DeclareRiichi(seat tile.Seat, id tile.TileID, points *Points) (Transition, play.Option[play.Refusal]) {
	if refusal := r.checkRiichi(seat, id, points.Score(seat)); refusal.OK {
		return Transition{}, refusal
	}

	tsumogiri := r.moveToRiver(seat, slices.Index(r.hand(seat), id), id)
	r.markRiichiDiscard(seat)
	return r.settleDiscard(seat, id, tsumogiri, points), play.Option[play.Refusal]{}
}

// Tsumo ends the round on seat's tsumo, paid with honba and the table's riichi sticks; any kan
// dora still pending stays hidden.
func (r *Round) Tsumo(seat tile.Seat, honba int, points Points) (Transition, play.Option[play.Refusal]) {
	win, ok := r.tsumoResult(seat, honba, points.RiichiSticks())
	if !ok {
		return Transition{}, notOffered(play.CodeNotOffered)
	}

	r.wall.ClearPendingDora()
	return ended(nil, play.Tsumo{Win: win}), play.Option[play.Refusal]{}
}

// Kyuushu aborts the round on seat's kyuushu kyuuhai.
func (r *Round) Kyuushu(seat tile.Seat) (Transition, play.Option[play.Refusal]) {
	if !r.mayKyuushu(seat) {
		return Transition{}, notOffered(play.CodeNotOffered)
	}

	result := play.Abortive{Kind: play.KyuushuKyuuhai{Seat: seat, Hand: r.Hand(seat)}}
	return ended(nil, result), play.Option[play.Refusal]{}
}

// DeclareKan announces seat's closed or added kan of id's kind, then offers it to the seats that
// may rob it, or, with none, lets it stand.
func (r *Round) DeclareKan(seat tile.Seat, kind play.KanKind, id tile.TileID) (Transition, play.Option[play.Refusal]) {
	kanTile, ok := r.checkKan(seat, kind, id)
	if !ok {
		return Transition{}, notOffered(play.CodeNotOffered)
	}

	robbable := r.openChankanPrompt(seat, kind, kanTile)
	meld := r.makeKan(seat, kind, kanTile)
	events := []play.Emitted{toAll(play.Called{Seat: seat, Meld: meld})}
	if !robbable {
		events = append(events, r.standKan(seat, kind)...)
	}
	return playing(events), play.Option[play.Refusal]{}
}

// AnswerCall records seat's answer to the open call prompt, then resolves the prompt once every
// seat has answered; a ron is paid with honba.
func (r *Round) AnswerCall(
	seat tile.Seat, action play.Action, honba int, points *Points,
) (Transition, play.Option[play.Refusal]) {
	prompt := r.prompt.Value
	switch {
	case !r.prompt.OK:
		return Transition{}, notAwaited(play.CodeSeatNotAwaited)
	case prompt.hasAnswered(seat):
		return Transition{}, notAwaited(play.CodeAlreadyAnswered)
	case !prompt.IsPending(seat):
		return Transition{}, notAwaited(play.CodeSeatNotAwaited)
	}

	declinesRon := action.Kind() != play.ActionRon && prompt.canRon(seat)
	if refusal := r.checkCall(seat, action); refusal.OK {
		return Transition{}, refusal
	}
	if declinesRon {
		r.declineRon(seat)
	}

	held, _ := action.Held()
	switch action.Kind() {
	case play.ActionRon:
		prompt.declareRon(seat)
	case play.ActionPon:
		prompt.declareMeld(seat, play.PonCall{Held: held})
	case play.ActionChi:
		prompt.declareMeld(seat, play.ChiCall{Held: held})
	case play.ActionKan:
		prompt.declareMeld(seat, play.OpenKanCall{})
	case play.ActionPass:
		prompt.pass(seat)
	case play.ActionDiscard, play.ActionRiichi, play.ActionTsumo, play.ActionKyuushu:
	}
	r.prompt = play.Some(prompt)

	if !prompt.isSettled() {
		return playing(nil), play.Option[play.Refusal]{}
	}
	return r.resolveCall(honba, points), play.Option[play.Refusal]{}
}

func (r *Round) settleDiscard(seat tile.Seat, id tile.TileID, tsumogiri bool, points *Points) Transition {
	riichi := r.undepositedRiichi.OK && r.undepositedRiichi.Value == seat
	events := make([]play.Emitted, 0, 1+tile.SeatCount)
	events = append(events, toAll(play.Discarded{Seat: seat, Tile: id, Tsumogiri: tsumogiri, Riichi: riichi}))
	events = append(events, doraRevealed(r.wall.RevealPendingDora())...)
	if r.isFourWinds() {
		return ended(events, play.Abortive{Kind: play.FourWinds{}})
	}

	if r.openCallPrompt(seat, id) {
		return playing(events)
	}

	events, result := r.passRonWindow(events, points)
	if result != nil {
		return ended(events, result)
	}
	return r.drawTurn(seat.Next(), events)
}

func (r *Round) passRonWindow(events []play.Emitted, points *Points) ([]play.Emitted, play.RoundResult) {
	if seat, ok := r.depositRiichi(); ok {
		events = append(events, points.depositRiichi(seat))
	}

	switch {
	case r.isFourRiichi():
		var hands []play.ShownHand
		for _, seat := range tile.Seats() {
			hands = append(hands, r.shownHand(seat))
		}
		return events, play.Abortive{Kind: play.FourRiichi{Hands: hands}}
	case r.isFourKans():
		return events, play.Abortive{Kind: play.FourKans{}}
	default:
		return events, nil
	}
}

func (r *Round) resolveCall(honba int, points *Points) Transition {
	prompt := r.prompt.Value
	r.prompt = play.Option[CallPrompt]{}
	rons := prompt.declaredRons()
	if len(rons) == 0 {
		return r.passCall(prompt, points)
	}

	if rules.TripleRonAbort && len(rons) > rules.DoubleRonCount {
		var hands []play.ShownHand
		for _, seat := range rons {
			hands = append(hands, r.shownHand(seat))
		}
		result := play.TripleRon{Discarder: prompt.from, Tile: prompt.tile, Hands: hands, RobbedKan: prompt.robbedKan()}
		return ended(nil, play.Abortive{Kind: result})
	}

	split := min(len(rons), rules.DoubleRonCount)
	wins := r.rons(rons[:split], prompt, honba, points.RiichiSticks())
	result := play.Ron{Discarder: prompt.from, Wins: wins, HeadBumped: slices.Clone(rons[split:])}
	return ended(nil, result)
}

func (r *Round) passCall(prompt CallPrompt, points *Points) Transition {
	if kind := prompt.robbedKan(); kind.OK {
		return playing(r.standKan(prompt.from, kind.Value))
	}

	events, result := r.passRonWindow(nil, points)
	if result != nil {
		return ended(events, result)
	}

	winning, ok := prompt.winningMeld()
	if !ok {
		return r.drawTurn(prompt.from.Next(), events)
	}

	meld, pao := r.call(winning.seat, winning.call, prompt.from, prompt.tile)
	events = append(events, toAll(play.Called{Seat: winning.seat, Meld: meld}))
	if pao.OK {
		events = append(events, toAll(play.PaoAssigned{Seat: winning.seat, Liable: pao.Value}))
	}
	if _, isKan := winning.call.(play.OpenKanCall); isKan {
		events = append(events, r.standKan(winning.seat, play.KanOpen)...)
	}
	return playing(events)
}

func (r *Round) standKan(seat tile.Seat, kind play.KanKind) []play.Emitted {
	r.endEveryIppatsu()
	events := doraRevealed(r.revealKanDora(kind))
	return appendDrawEvents(events, seat, r.drawRinshan(seat), true)
}

func (r *Round) drawTurn(seat tile.Seat, events []play.Emitted) Transition {
	id, ok := r.draw(seat)
	if !ok {
		return ended(events, r.exhaustiveDraw())
	}
	return playing(appendDrawEvents(events, seat, id, false))
}

func (r *Round) draw(seat tile.Seat) (tile.TileID, bool) {
	r.current = seat
	id, ok := r.wall.Draw()
	if !ok {
		return tile.TileID{}, false
	}

	r.latestDiscard = play.Option[tile.Seat]{}
	r.hands[seat.Index()].push(id)
	r.drawn = play.Some(id)
	r.rinshan = false
	return id, true
}

func (r *Round) drawRinshan(seat tile.Seat) tile.TileID {
	id, _ := r.wall.DrawRinshan()
	r.hands[seat.Index()].push(id)
	r.drawn = play.Some(id)
	r.rinshan = true
	return id
}

// TurnActions returns every action of seat on its turn with score points: the discards in hand
// order, the riichi discards, tsumo, the kans and kyuushu.
func (r *Round) TurnActions(seat tile.Seat, score int) []play.Action {
	var actions []play.Action
	for _, id := range offer.TurnDiscards(r.hand(seat), r.drawn, r.InRiichi(seat), r.kuikae) {
		actions = append(actions, play.DiscardAction(id))
	}
	for _, id := range r.riichiDiscards(seat, score) {
		actions = append(actions, play.RiichiAction(id))
	}
	if _, _, ok := r.tsumoWin(seat); ok {
		actions = append(actions, play.TsumoAction())
	}
	actions = append(actions, r.kanOffers(seat)...)
	if r.mayKyuushu(seat) {
		actions = append(actions, play.KyuushuAction())
	}
	return actions
}

func (r *Round) riichiDiscards(seat tile.Seat, score int) []tile.TileID {
	return offer.RiichiDiscards(r.hand(seat), r.seatMelds(seat), r.InRiichi(seat), score, r.LiveTiles())
}

func (r *Round) kanOffers(seat tile.Seat) []play.Action {
	if !r.drawn.OK {
		return nil
	}
	kans := offer.KansBySeat(r.meldsBySeat())
	return offer.KanOffers(r.hand(seat), r.seatMelds(seat), r.drawn.Value, r.InRiichi(seat), kans, r.LiveTiles())
}

func (r *Round) checkKan(seat tile.Seat, kind play.KanKind, id tile.TileID) (tile.TileID, bool) {
	for _, offered := range r.kanOffers(seat) {
		offeredKind, _ := offered.Kan()
		held, _ := offered.Tile()
		if offeredKind == kind && held.Kind() == id.Kind() {
			return kanTile(kind, id, held), true
		}
	}
	return tile.TileID{}, false
}

func kanTile(kind play.KanKind, named, held tile.TileID) tile.TileID {
	if kind == play.KanClosed {
		return named
	}
	return held
}

func (r *Round) openChankanPrompt(seat tile.Seat, kind play.KanKind, id tile.TileID) bool {
	var robbers []tile.Seat
	for _, other := range tile.Seats() {
		if other != seat && offer.MayRobKan(r.ronCandidate(other), kind, id) {
			robbers = append(robbers, other)
		}
	}
	if len(robbers) == 0 {
		return false
	}

	r.prompt = play.Some(newChankanPrompt(id, seat, kind, robbers))
	return true
}

func (r *Round) makeKan(seat tile.Seat, kind play.KanKind, id tile.TileID) play.MeldView {
	held, melds := &r.hands[seat.Index()], &r.melds[seat.Index()]
	var meld play.MeldView
	if kind == play.KanClosed {
		tiles := slices.Collect(tile.HeldCopies(held.view(), id.Kind()))
		slices.SortFunc(tiles, tile.TileID.Compare)
		held.keep(func(other tile.TileID) bool { return other.Kind() != id.Kind() })
		meld = play.MeldView{Kind: play.MeldClosedKan, Tiles: tiles}
		melds.push(meld)
	} else {
		held.keep(func(other tile.TileID) bool { return other != id })
		meld = melds.addToPon(id)
	}

	r.current = seat
	r.drawn = play.Option[tile.TileID]{}
	return meld
}

func (r *Round) endEveryIppatsu() {
	for i := range r.riichi {
		r.riichi[i].Value.Ippatsu = false
	}
}

func (r *Round) revealKanDora(kind play.KanKind) []tile.TileID {
	revealed := r.wall.RevealPendingDora()
	if kind == play.KanClosed && rules.KanDoraImmediateForClosedKan {
		indicator, _ := r.wall.AddDoraIndicator()
		return append(revealed, indicator)
	}
	_ = r.wall.IncrementPendingDora()
	return revealed
}

func (r *Round) isFourKans() bool {
	return offer.IsFourKans(offer.KansBySeat(r.meldsBySeat()))
}

func (r *Round) mayKyuushu(seat tile.Seat) bool {
	return len(r.rivers[seat.Index()]) == 0 && !r.hasAnyCall() && offer.HasNineTerminalKinds(r.hand(seat))
}

func (r *Round) checkDiscard(seat tile.Seat, id tile.TileID) (int, play.Option[play.Refusal]) {
	position := slices.Index(r.hand(seat), id)
	switch {
	case position < 0:
		return 0, notOffered(play.CodeTileNotHeld)
	case r.InRiichi(seat) && (!r.drawn.OK || r.drawn.Value != id):
		return 0, ruleRefusal(play.CodeRiichiDrawnTileOnly)
	case slices.Contains(r.kuikae, id.Kind()):
		return 0, ruleRefusal(play.CodeKuikae)
	default:
		return position, play.Option[play.Refusal]{}
	}
}

func (r *Round) moveToRiver(seat tile.Seat, position int, id tile.TileID) bool {
	i := seat.Index()
	r.kuikae = nil
	r.hands[i].removeAt(position)
	tsumogiri := r.drawn.OK && r.drawn.Value == id
	r.drawn = play.Option[tile.TileID]{}
	r.rivers[i] = appendTo(r.rivers[i], play.RiverTile{Tile: id, Tsumogiri: tsumogiri})
	r.latestDiscard = play.Some(seat)
	r.rinshan = false
	r.furiten[i].Temporary = false
	r.riichi[i].Value.Ippatsu = false
	return tsumogiri
}

func (r *Round) checkRiichi(seat tile.Seat, id tile.TileID, score int) play.Option[play.Refusal] {
	discards := r.riichiDiscards(seat, score)
	switch {
	case len(discards) == 0:
		return notOffered(play.CodeNotOffered)
	case !slices.Contains(r.hand(seat), id):
		return notOffered(play.CodeTileNotHeld)
	case !slices.Contains(discards, id):
		return ruleRefusal(play.CodeRiichiBreaksTenpai)
	default:
		return play.Option[play.Refusal]{}
	}
}

func (r *Round) markRiichiDiscard(seat tile.Seat) {
	i := seat.Index()
	r.undepositedRiichi = play.Some(seat)
	river := slices.Clone(r.rivers[i])
	river[len(river)-1].Riichi = true
	r.rivers[i] = river
}

func (r *Round) depositRiichi() (tile.Seat, bool) {
	seat, ok := r.undepositedRiichi.Value, r.undepositedRiichi.OK
	if !ok {
		return tile.Seat{}, false
	}

	r.undepositedRiichi = play.Option[tile.Seat]{}
	r.riichi[seat.Index()] = play.Some(play.Riichi{
		Double:  len(r.rivers[seat.Index()]) == 1 && !r.hasAnyCall(),
		Ippatsu: true,
	})
	return seat, true
}

func (r *Round) isFourRiichi() bool {
	for _, riichi := range r.riichi {
		if !riichi.OK {
			return false
		}
	}
	return true
}

func (r *Round) isFourWinds() bool {
	total := 0
	for _, river := range r.rivers {
		total += len(river)
	}
	if total != rules.FourWindsDiscardCount || r.hasAnyCall() {
		return false
	}

	discards := make([]tile.TileID, 0, rules.FourWindsDiscardCount)
	for _, river := range r.rivers {
		for _, discard := range river {
			discards = append(discards, discard.Tile)
		}
	}
	return offer.IsFourWinds(discards)
}

func (r *Round) openCallPrompt(from tile.Seat, id tile.TileID) bool {
	var callers []tile.Seat
	for _, seat := range tile.Seats() {
		if seat == from {
			continue
		}
		switch r.ronOutcome(seat, id) {
		case offer.RonNotComplete:
		case offer.RonMissed:
			r.furiten[seat.Index()] = r.furiten[seat.Index()].MissRon(r.InRiichi(seat))
		case offer.RonOffered:
			callers = append(callers, seat)
		}
	}

	var meldOffers [tile.SeatCount][]play.Action
	anyMeld := false
	kans := offer.KansBySeat(r.meldsBySeat())
	for _, seat := range tile.Seats() {
		meldOffers[seat.Index()] = r.meldOffers(seat, from, id, kans)
		anyMeld = anyMeld || len(meldOffers[seat.Index()]) > 0
	}
	if len(callers) == 0 && !anyMeld {
		return false
	}

	r.prompt = play.Some(newCallPrompt(id, from, callers, meldOffers))
	return true
}

func (r *Round) meldOffers(seat, from tile.Seat, id tile.TileID, kans [tile.SeatCount]int) []play.Action {
	return offer.MeldOffers(r.hand(seat), r.InRiichi(seat), seat, from, id, kans, r.LiveTiles())
}

func (r *Round) checkCall(seat tile.Seat, action play.Action) play.Option[play.Refusal] {
	offers := r.prompt.Value.Offers(seat)
	held, _ := action.Held()
	if kind, isKan := action.Kan(); isKan && kind == play.KanOpen {
		called, _ := action.Tile()
		return refusedUnless(slices.ContainsFunc(offers, func(offered play.Action) bool {
			offeredKind, isOfferedKan := offered.Kan()
			offeredTile, _ := offered.Tile()
			return isOfferedKan && offeredKind == play.KanOpen && offeredTile.Kind() == called.Kind()
		}))
	}

	if action.Kind() == play.ActionPon {
		ponKind, offered := ponKindOf(offers)
		if !offered {
			return notOffered(play.CodeNotOffered)
		}
		if refusal := r.checkHeldPair(seat, held); refusal.OK {
			return refusal
		}
		return refusedUnless(held[0].Kind() == ponKind && held[1].Kind() == ponKind)
	}

	if action.Kind() != play.ActionChi {
		return refusedUnless(slices.Contains(offers, action))
	}

	chiKinds := chiKindsOf(offers)
	if len(chiKinds) == 0 {
		return notOffered(play.CodeNotOffered)
	}
	if refusal := r.checkHeldPair(seat, held); refusal.OK {
		return refusal
	}
	return refusedUnless(slices.Contains(chiKinds, sortedKinds(held)))
}

func ponKindOf(offers []play.Action) (tile.Kind, bool) {
	for _, offered := range offers {
		if held, _ := offered.Held(); offered.Kind() == play.ActionPon {
			return held[0].Kind(), true
		}
	}
	return 0, false
}

func chiKindsOf(offers []play.Action) [][2]tile.Kind {
	var kinds [][2]tile.Kind
	for _, offered := range offers {
		if held, _ := offered.Held(); offered.Kind() == play.ActionChi {
			kinds = append(kinds, sortedKinds(held))
		}
	}
	return kinds
}

func (r *Round) checkHeldPair(seat tile.Seat, pair [2]tile.TileID) play.Option[play.Refusal] {
	held := r.hand(seat)
	if pair[0] == pair[1] || !slices.Contains(held, pair[0]) || !slices.Contains(held, pair[1]) {
		return notOffered(play.CodeTileNotHeld)
	}
	return play.Option[play.Refusal]{}
}

func (r *Round) call(seat tile.Seat, call play.MeldCall, from tile.Seat, id tile.TileID) (
	play.MeldView, play.Option[tile.Seat],
) {
	i := seat.Index()
	var kind play.MeldKind
	var taken []tile.TileID
	switch c := call.(type) {
	case play.PonCall:
		kind, taken = play.MeldPon, c.Held[:]
	case play.ChiCall:
		kind, taken = play.MeldChi, c.Held[:]
	case play.OpenKanCall:
		kind = play.MeldOpenKan
		for held := range tile.HeldCopies(r.hand(seat), id.Kind()) {
			taken = append(taken, held)
		}
		taken = taken[:min(len(taken), offer.OpenKanHandTiles)]
	}

	r.hands[i].keep(func(held tile.TileID) bool { return !slices.Contains(taken, held) })
	meld := offer.NewMeldView(kind, id, taken, from)
	pao := offer.PaoOfMeld(r.seatMelds(seat), meld)
	if pao.OK && !r.pao[i].OK {
		r.pao[i] = pao
	} else {
		pao = play.Option[tile.Seat]{}
	}

	r.melds[i].push(meld)
	r.kuikae = offer.KuikaeKinds(id, call)
	r.endEveryIppatsu()
	r.current = seat
	r.drawn = play.Option[tile.TileID]{}
	r.latestDiscard = play.Option[tile.Seat]{}
	return meld, pao
}

func (r *Round) ronOutcome(seat tile.Seat, id tile.TileID) offer.RonOutcome {
	win := offer.RonWin(play.SourceDiscard, r.LiveTiles())
	return offer.DiscardRon(r.ronCandidate(seat), id, r.situation(seat, win))
}

func (r *Round) ronCandidate(seat tile.Seat) offer.RonCandidate {
	return offer.RonCandidate{
		Hand:       r.hand(seat),
		Melds:      r.seatMelds(seat),
		River:      r.rivers[seat.Index()],
		Furiten:    r.furiten[seat.Index()],
		KnownWaits: r.hands[seat.Index()].waitsUntilHandMoves,
	}
}

func (r *Round) declineRon(seat tile.Seat) {
	i := seat.Index()
	r.furiten[i] = r.furiten[i].DeclineRon(r.InRiichi(seat))
}

func (r *Round) waits(seat tile.Seat) tile.Kinds {
	held := &r.hands[seat.Index()]
	if !held.waitsUntilHandMoves.OK {
		held.waitsUntilHandMoves = play.Some(hand.Waits(countsOf(held.view()), countsOf(r.meldedTiles(seat))))
	}
	return held.waitsUntilHandMoves.Value
}

func (r *Round) seatWind(seat tile.Seat) tile.Wind {
	return seat.Wind(r.dealer)
}

func (r *Round) isAwaitingChankanOn(seat tile.Seat) bool {
	return r.prompt.OK && r.prompt.Value.robbedKan().OK && r.prompt.Value.from == seat
}

func (r *Round) shownFuriten(seat tile.Seat) bool {
	furiten := r.furiten[seat.Index()]
	if r.hands[seat.Index()].count%3 == drawnHandRemainder {
		return furiten.Shown || furiten.BlocksRon()
	}
	river := r.rivers[seat.Index()]
	return furiten.BlocksRon() || (len(river) > 0 && offer.IsDiscardFuriten(r.waits(seat), river))
}

// ReportFuriten shows each seat its changed furiten, a drawn hand keeping its turn's value unless
// a flag was set since; a kan's declarer waits out its chankan prompt.
func (r *Round) ReportFuriten() []play.Emitted {
	var events []play.Emitted
	for _, seat := range tile.Seats() {
		if r.isAwaitingChankanOn(seat) {
			continue
		}

		furiten := r.shownFuriten(seat)
		if r.furiten[seat.Index()].Shown != furiten {
			r.furiten[seat.Index()].Shown = furiten
			events = append(events, toSeat(seat, play.FuritenChanged{Seat: seat, Furiten: furiten}))
		}
	}
	return events
}

// CheckOwnership checks that each of the 136 tiles is in exactly one place: the wall, a hand, a
// meld or a river, a called tile counting in its discarder's river and not in the meld. The
// error is wall.CheckOwnership's.
func (r *Round) CheckOwnership() error {
	return wall.CheckOwnership(r.wall, slices.Values(r.heldTiles()))
}

func (r *Round) heldTiles() []tile.TileID {
	var held []tile.TileID
	for i := range r.hands {
		held = append(held, r.hands[i].view()...)
	}
	for _, river := range r.rivers {
		for _, discard := range river {
			held = append(held, discard.Tile)
		}
	}
	for i := range r.melds {
		for _, view := range r.melds[i].view() {
			for _, id := range view.Tiles {
				if !view.Called.OK || view.Called.Value != id {
					held = append(held, id)
				}
			}
		}
	}
	return held
}

func appendDrawEvents(events []play.Emitted, seat tile.Seat, id tile.TileID, rinshan bool) []play.Emitted {
	events = append(slices.Grow(events, tile.SeatCount), toSeat(seat, play.Drew{Seat: seat, Tile: id, Rinshan: rinshan}))
	var notice play.Event = play.DrewNotice{Seat: seat, Rinshan: rinshan}
	for _, other := range tile.Seats() {
		if other != seat {
			events = append(events, toSeat(other, notice))
		}
	}
	return events
}

func doraRevealed(indicators []tile.TileID) []play.Emitted {
	var events []play.Emitted
	for _, indicator := range indicators {
		events = append(events, toAll(play.DoraRevealed{Indicator: indicator}))
	}
	return events
}

func sortedKinds(pair [2]tile.TileID) [2]tile.Kind {
	a, b := pair[0].Kind(), pair[1].Kind()
	return [2]tile.Kind{min(a, b), max(a, b)}
}

func countsOf(ids []tile.TileID) tile.Counts {
	counts, _ := tile.KindCounts(ids)
	return counts
}

func toAll(event play.Event) play.Emitted {
	return play.Emitted{To: play.ToAll(), Event: event}
}

func toSeat(seat tile.Seat, event play.Event) play.Emitted {
	return play.Emitted{To: play.ToSeat(seat), Event: event}
}

func notOffered(code play.RefusalCode) play.Option[play.Refusal] {
	return play.Some(play.Refusal{Kind: play.RefusalNotOffered, Code: code})
}

func notAwaited(code play.RefusalCode) play.Option[play.Refusal] {
	return play.Some(play.Refusal{Kind: play.RefusalNotAwaited, Code: code})
}

func ruleRefusal(code play.RefusalCode) play.Option[play.Refusal] {
	return play.Some(play.Refusal{Kind: play.RefusalRule, Code: code})
}

func refusedUnless(offered bool) play.Option[play.Refusal] {
	if offered {
		return play.Option[play.Refusal]{}
	}
	return notOffered(play.CodeNotOffered)
}
