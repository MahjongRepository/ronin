package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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
		Hand:      r.hand(seat),
		Melds:     r.seatMelds(seat),
		River:     r.rivers[seat.Index()],
		Furiten:   r.furiten[seat.Index()],
		HandWaits: r.hands[seat.Index()].waitsUntilHandMoves,
	}
}
