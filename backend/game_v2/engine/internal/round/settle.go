package round

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func (r *Round) situation(seat tile.Seat, win score.Win) score.Situation {
	situation := offer.BaseSituation(win, r.seatWind(seat), r.roundWind, r.riichi[seat.Index()])
	situation.FirstTurn = win.IsTsumo() && len(r.rivers[seat.Index()]) == 0 && !r.hasAnyCall()
	return situation
}

func (r *Round) uraIndicators(seat tile.Seat) []tile.TileID {
	if !r.InRiichi(seat) {
		return nil
	}

	return r.wall.UraIndicators()
}

func (r *Round) scoring(seat tile.Seat, win score.Win) offer.Scoring {
	return offer.Scoring{
		Situation:      r.situation(seat, win),
		Melds:          r.seatMelds(seat),
		DoraIndicators: r.wall.DoraIndicators(),
		UraIndicators:  r.uraIndicators(seat),
	}
}

func (r *Round) tsumoWin(seat tile.Seat) (tile.TileID, score.HandValue, bool) {
	held := r.hand(seat)
	last := len(held) - 1
	if seat != r.current || !r.drawn.OK || last < 0 || held[last] != r.drawn.Value ||
		!offer.Completes(held[:last], held[last]) {
		return tile.TileID{}, score.HandValue{}, false
	}

	win := score.WinTsumo
	switch {
	case r.rinshan:
		win = score.WinRinshan
	case r.LiveTiles() == 0:
		win = score.WinHaitei
	}

	value, ok := offer.OfferedValue(held[:last], held[last], r.scoring(seat, win))
	return held[last], value, ok
}

func (r *Round) winResult(
	winner tile.Seat, loser play.Option[tile.Seat], winTile tile.TileID, value score.HandValue,
	changes [tile.SeatCount]int,
) play.WinResult {
	concealed := r.Hand(winner)
	if !loser.OK {
		concealed = concealed[:len(concealed)-1]
	}

	yaku := make([]play.YakuID, len(value.Yaku))
	for i, scored := range value.Yaku {
		yaku[i] = scored.ID
	}

	return play.WinResult{
		Winner:        winner,
		Loser:         loser,
		Hand:          concealed,
		Melds:         r.Melds(winner),
		WinTile:       winTile,
		Value:         value.Value,
		Limit:         value.Limit,
		Yaku:          yaku,
		Dora:          value.Dora,
		UraIndicators: r.uraIndicators(winner),
		Pao:           r.pao[winner.Index()],
		ScoreChanges:  changes,
	}
}

func (r *Round) tsumoResult(seat tile.Seat, honba, riichiSticks int) (play.WinResult, bool) {
	winTile, value, ok := r.tsumoWin(seat)
	if !ok {
		return play.WinResult{}, false
	}

	changes := offer.TsumoScoreChanges(seat, r.dealer, value.Payment, honba, riichiSticks, r.pao[seat.Index()])
	return r.winResult(seat, play.Option[tile.Seat]{}, winTile, value, changes), true
}

func (r *Round) rons(winners []tile.Seat, prompt CallPrompt, honba, riichiSticks int) []play.WinResult {
	win := offer.RonWin(prompt.source, r.LiveTiles())
	wins := make([]play.WinResult, 0, len(winners))
	for position, winner := range winners {
		value := offer.SettledValue(r.hand(winner), prompt.tile, r.scoring(winner, win))
		tableHonba, tableSticks := offer.RonTableShare(position, honba, riichiSticks)
		pao := r.pao[winner.Index()]
		changes := offer.RonScoreChanges(winner, prompt.from, value.Payment, tableHonba, tableSticks, pao)
		wins = append(wins, r.winResult(winner, play.Some(prompt.from), prompt.tile, value, changes))
	}

	return wins
}

func (r *Round) exhaustiveDraw() play.RoundResult {
	var tenpaiSeats [tile.SeatCount]bool
	for _, seat := range tile.Seats() {
		tenpaiSeats[seat.Index()] = isKeishikiTenpai(r.hand(seat), r.meldedTiles(seat))
	}

	var nagashi []tile.Seat
	if rules.NagashiMangan {
		nagashi = offer.NagashiSeats(r.rivers, r.meldsBySeat())
	}

	scoreChanges := notenPayments(tenpaiSeats)
	if len(nagashi) > 0 {
		scoreChanges = r.nagashiPayments(nagashi)
	}

	result := play.ExhaustiveDraw{ScoreChanges: scoreChanges}
	for _, seat := range tile.Seats() {
		if tenpaiSeats[seat.Index()] {
			result.Tenpai = append(result.Tenpai, r.shownHand(seat))
		}
	}

	for _, seat := range nagashi {
		result.Nagashi = append(result.Nagashi, play.NagashiRiver{Seat: seat, River: r.River(seat)})
	}

	return result
}

func (r *Round) shownHand(seat tile.Seat) play.ShownHand {
	return play.ShownHand{Seat: seat, Hand: r.Hand(seat), Melds: r.Melds(seat)}
}

func (r *Round) nagashiPayments(nagashi []tile.Seat) [tile.SeatCount]int {
	var total [tile.SeatCount]int
	for _, seat := range nagashi {
		payment := score.NagashiMangan(r.seatWind(seat))
		changes := offer.TsumoScoreChanges(seat, r.dealer, payment, 0, 0, play.Option[tile.Seat]{})
		for i, change := range changes {
			total[i] += change
		}
	}

	return total
}

func isKeishikiTenpai(closed, melded []tile.TileID) bool {
	return hand.IsTenpai(countsOf(closed), countsOf(melded))
}

func notenPayments(tenpai [tile.SeatCount]bool) [tile.SeatCount]int {
	tenpaiCount := 0
	for _, isTenpai := range tenpai {
		if isTenpai {
			tenpaiCount++
		}
	}

	notenCount := tile.SeatCount - tenpaiCount
	if tenpaiCount == 0 || notenCount == 0 {
		return [tile.SeatCount]int{}
	}

	gain, loss := rules.NotenPenaltyTotal/tenpaiCount, rules.NotenPenaltyTotal/notenCount
	var payments [tile.SeatCount]int
	for i, isTenpai := range tenpai {
		payments[i] = -loss
		if isTenpai {
			payments[i] = gain
		}
	}

	return payments
}
