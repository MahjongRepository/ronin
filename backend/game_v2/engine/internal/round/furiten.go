package round

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const drawnHandRemainder = 2

// ShownFuriten returns the furiten seat was last shown.
func (r *Round) ShownFuriten(seat tile.Seat) bool {
	return r.furiten[seat.Index()].Shown
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
