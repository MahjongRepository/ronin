package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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

func (r *Round) seatWind(seat tile.Seat) tile.Wind {
	return seat.Wind(r.dealer)
}

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

func appendTo[T any](s []T, items ...T) []T {
	return append(slices.Clip(s), items...)
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
