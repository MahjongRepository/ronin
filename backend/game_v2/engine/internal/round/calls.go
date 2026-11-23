package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// CallPrompt is the call prompt on a discard, or on a kan a chankan may rob: who may call the tile
// and how, who still owes an answer and what they answered.
type CallPrompt struct {
	tile       tile.TileID
	from       tile.Seat
	source     play.CallSource
	ronCallers []tile.Seat
	meldOffers [tile.SeatCount][]play.Action
	pending    []tile.Seat
	rons       []tile.Seat
	meldCalls  []seatCall
}

type seatCall struct {
	seat tile.Seat
	call play.MeldCall
}

func newCallPrompt(
	id tile.TileID, from tile.Seat, ronCallers []tile.Seat, meldOffers [tile.SeatCount][]play.Action,
) CallPrompt {
	callers := slices.Clone(ronCallers)
	slices.SortFunc(callers, func(a, b tile.Seat) int { return a.DistanceFrom(from) - b.DistanceFrom(from) })
	var pending []tile.Seat
	for _, seat := range tile.Seats() {
		if slices.Contains(callers, seat) || len(meldOffers[seat.Index()]) > 0 {
			pending = append(pending, seat)
		}
	}
	return CallPrompt{
		tile:       id,
		from:       from,
		source:     play.SourceDiscard,
		ronCallers: callers,
		meldOffers: meldOffers,
		pending:    pending,
	}
}

func newChankanPrompt(id tile.TileID, from tile.Seat, kind play.KanKind, robbers []tile.Seat) CallPrompt {
	prompt := newCallPrompt(id, from, robbers, [tile.SeatCount][]play.Action{})
	prompt.source = play.SourceAddedKan
	if kind == play.KanClosed {
		prompt.source = play.SourceClosedKan
	}
	return prompt
}

// Source returns what the prompt offers its tile from.
func (p CallPrompt) Source() play.CallSource {
	return p.source
}

func (p CallPrompt) robbedKan() play.Option[play.KanKind] {
	switch p.source {
	case play.SourceAddedKan:
		return play.Some(play.KanAdded)
	case play.SourceClosedKan:
		return play.Some(play.KanClosed)
	case play.SourceDiscard:
	}
	return play.Option[play.KanKind]{}
}

// Tile returns the tile the prompt offers.
func (p CallPrompt) Tile() tile.TileID {
	return p.tile
}

// From returns the seat whose discard or kan the prompt is on.
func (p CallPrompt) From() tile.Seat {
	return p.from
}

// Pending returns the seats still to answer, in seat order.
func (p CallPrompt) Pending() []tile.Seat {
	return slices.Clone(p.pending)
}

// IsPending reports whether seat still owes an answer.
func (p CallPrompt) IsPending(seat tile.Seat) bool {
	return slices.Contains(p.pending, seat)
}

func (p CallPrompt) canRon(seat tile.Seat) bool {
	return slices.Contains(p.ronCallers, seat)
}

func (p CallPrompt) isCaller(seat tile.Seat) bool {
	return p.canRon(seat) || len(p.meldOffers[seat.Index()]) > 0
}

// Offers returns every answer the prompt offers seat: ron, its meld calls (an open kan, one pon
// per look, then one chi per shape), then pass; none for a seat it does not call on.
func (p CallPrompt) Offers(seat tile.Seat) []play.Action {
	if !p.isCaller(seat) {
		return nil
	}

	var offers []play.Action
	if p.canRon(seat) {
		offers = append(offers, play.RonAction())
	}
	offers = append(offers, p.meldOffers[seat.Index()]...)
	return append(offers, play.PassAction())
}

func (p CallPrompt) hasAnswered(seat tile.Seat) bool {
	return p.isCaller(seat) && !p.IsPending(seat)
}

func (p *CallPrompt) recordAnswer(seat tile.Seat, action play.Action) {
	held, _ := action.Held()
	switch action.Kind() {
	case play.ActionRon:
		p.rons = appendTo(p.rons, seat)
	case play.ActionPon:
		p.meldCalls = appendTo(p.meldCalls, seatCall{seat, play.PonCall{Held: held}})
	case play.ActionChi:
		p.meldCalls = appendTo(p.meldCalls, seatCall{seat, play.ChiCall{Held: held}})
	case play.ActionKan:
		p.meldCalls = appendTo(p.meldCalls, seatCall{seat, play.OpenKanCall{}})
	case play.ActionPass, play.ActionDiscard, play.ActionRiichi, play.ActionTsumo, play.ActionKyuushu:
	}

	onlyRon := action.Kind() == play.ActionRon || action.Kind() == play.ActionPon || action.Kind() == play.ActionKan
	var pending []tile.Seat
	for _, other := range p.pending {
		if other == seat {
			continue
		}
		if onlyRon && !p.canRon(other) {
			p.meldOffers[other.Index()] = nil
			continue
		}
		pending = append(pending, other)
	}
	p.pending = pending
}

func (p CallPrompt) isSettled() bool {
	return len(p.pending) == 0
}

func (p CallPrompt) declaredRons() []tile.Seat {
	var rons []tile.Seat
	for _, seat := range p.ronCallers {
		if slices.Contains(p.rons, seat) {
			rons = append(rons, seat)
		}
	}
	return rons
}

func (p CallPrompt) winningMeld() (seatCall, bool) {
	for _, declared := range p.meldCalls {
		if _, isChi := declared.call.(play.ChiCall); !isChi {
			return declared, true
		}
	}
	if len(p.meldCalls) == 0 {
		return seatCall{}, false
	}
	return p.meldCalls[0], true
}
