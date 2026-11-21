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

func (r *Round) endsOnceItsPromptPasses() bool {
	if !r.prompt.OK || r.prompt.Value.robbedKan().OK {
		return false
	}

	lastRiichi := r.undepositedRiichi.OK
	for _, seat := range tile.Seats() {
		lastRiichi = lastRiichi && (r.InRiichi(seat) || r.undepositedRiichi.Value == seat)
	}
	return r.LiveTiles() == 0 || r.isFourKans() || lastRiichi
}

// ReportFuriten shows each seat its changed furiten, a drawn hand keeping its turn's value unless
// a flag was set since; a kan's declarer waits out its chankan prompt. It shows nothing while a
// prompt is open on a discard that ends the round even when every seat passes (the wall's last, the
// fourth riichi, the one after the fourth kan), since the round ends at once when nobody may call
// it, so a change shown here would tell its seat that another may win on the discard.
func (r *Round) ReportFuriten() []play.Emitted {
	if r.endsOnceItsPromptPasses() {
		return nil
	}

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
