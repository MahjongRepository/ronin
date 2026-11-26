package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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

func (r *Round) drawTurn(seat tile.Seat, events []play.Emitted) Transition {
	id, ok := r.draw(seat)
	if !ok {
		return ended(events, r.exhaustiveDraw())
	}

	return playing(appendDrawEvents(events, seat, id, liveDraw))
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

func (r *Round) endEveryIppatsu() {
	for i := range r.riichi {
		r.riichi[i].Value.Ippatsu = false
	}
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
