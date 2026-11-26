package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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

func (r *Round) standKan(seat tile.Seat, kind play.KanKind) []play.Emitted {
	r.endEveryIppatsu()
	events := doraRevealed(r.revealKanDora(kind))
	return appendDrawEvents(events, seat, r.drawRinshan(seat), rinshanDraw)
}

func (r *Round) drawRinshan(seat tile.Seat) tile.TileID {
	id, _ := r.wall.DrawRinshan()
	r.hands[seat.Index()].push(id)
	r.drawn = play.Some(id)
	r.rinshan = true
	return id
}

func (r *Round) kanOffers(seat tile.Seat) []play.Action {
	if !r.drawn.OK {
		return nil
	}

	kans := offer.KansBySeat(r.meldsBySeat())
	return offer.KanOffers(r.hand(seat), r.seatMelds(seat), r.drawn.Value, r.InRiichi(seat), kans, r.LiveTiles(), r.ruleset)
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

func (r *Round) revealKanDora(kind play.KanKind) []tile.TileID {
	revealed := r.wall.RevealPendingDora()
	settings := r.settings()
	immediate := settings.KanDoraImmediateForOpenKan
	if kind == play.KanClosed {
		immediate = settings.KanDoraImmediateForClosedKan
	}

	if immediate {
		indicator, _ := r.wall.AddDoraIndicator()
		return append(revealed, indicator)
	}

	_ = r.wall.IncrementPendingDora()
	return revealed
}

func (r *Round) isFourKans() bool {
	return offer.IsFourKans(offer.KansBySeat(r.meldsBySeat()), r.ruleset)
}
