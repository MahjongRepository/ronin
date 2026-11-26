package offer

import (
	"errors"
	"fmt"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Completes reports whether the concealed tiles with winTile added form a complete hand.
func Completes(concealed []tile.TileID, winTile tile.TileID) bool {
	var joined [tile.MaxConcealedTiles]tile.TileID
	counts, err := tile.KindCounts(append(append(joined[:0], concealed...), winTile))
	return err == nil && hand.IsAgari(counts)
}

// Scoring is what a win is scored from besides the tiles. UraIndicators is empty unless the
// winner is in riichi.
type Scoring struct {
	Situation      score.Situation
	Melds          []play.MeldView
	DoraIndicators []tile.TileID
	UraIndicators  []tile.TileID
}

func HandValue(concealed []tile.TileID, winTile tile.TileID, scoring Scoring) (score.HandValue, error) {
	melds := make([]meld.Meld, 0, len(scoring.Melds))
	for index, view := range scoring.Melds {
		m, ok := meld.FromView(view)
		if !ok {
			return score.HandValue{}, meld.MisfitMeldError{Index: index}
		}

		melds = append(melds, m)
	}

	h := score.Hand{Concealed: tilesOf(concealed), WinTile: winTile.Tile(rules.AkaDora), Melds: melds}
	dora := score.Dora{Indicators: tilesOf(scoring.DoraIndicators), UraIndicators: tilesOf(scoring.UraIndicators)}
	return score.EstimateHandValue(h, scoring.Situation, dora, score.HandRules())
}

func OfferedValue(concealed []tile.TileID, winTile tile.TileID, scoring Scoring) (score.HandValue, bool) {
	value, err := HandValue(concealed, winTile, scoring)
	if errors.Is(err, score.NoYakuError{}) {
		return score.HandValue{}, false
	}

	if err != nil {
		panic(play.EngineFaultError{Err: err})
	}

	return value, true
}

// SettledValue returns HandValue's value of a win being settled. It panics with a
// play.EngineFaultError on any scorer error, since the win was offered.
func SettledValue(concealed []tile.TileID, winTile tile.TileID, scoring Scoring) score.HandValue {
	value, err := HandValue(concealed, winTile, scoring)
	if err != nil {
		panic(play.EngineFaultError{Err: err})
	}

	return value
}

type MisfitPaymentError struct {
	Payment play.Payment
}

func (e MisfitPaymentError) Error() string {
	return fmt.Sprintf("the payment %T%+v does not fit the win", e.Payment, e.Payment)
}

func tilesOf(ids []tile.TileID) []tile.Tile {
	tiles := make([]tile.Tile, len(ids))
	for i, id := range ids {
		tiles[i] = id.Tile(rules.AkaDora)
	}

	return tiles
}

func TsumoScoreChanges(
	winner, dealer tile.Seat, payment play.Payment, honba, riichiSticks int, pao play.Option[tile.Seat],
) [tile.SeatCount]int {
	dealerShare, nonDealerShare := tsumoShares(payment, winner == dealer)
	honbaPerPayer := score.HonbaBonus(score.WinTsumo, honba)
	var changes [tile.SeatCount]int
	for _, payer := range tile.Seats() {
		if payer == winner {
			continue
		}

		paid := nonDealerShare + honbaPerPayer
		if payer == dealer {
			paid = dealerShare + honbaPerPayer
		}

		charged := payer
		if pao.OK {
			charged = pao.Value
		}

		changes[charged.Index()] -= paid
		changes[winner.Index()] += paid
	}

	changes[winner.Index()] += score.RiichiSticksBonus(riichiSticks)
	return changes
}

func tsumoShares(payment play.Payment, winnerIsDealer bool) (dealerShare, nonDealerShare int) {
	switch p := payment.(type) {
	case play.TsumoPayment:
		if !winnerIsDealer {
			return p.Dealer, p.NonDealer
		}
	case play.DealerTsumoPayment:
		if winnerIsDealer {
			return p.NonDealer, p.NonDealer
		}
	case play.RonPayment:
	}

	panic(play.EngineFaultError{Err: MisfitPaymentError{Payment: payment}})
}

func RonTableShare(position, honba, riichiSticks int) (tableHonba, tableSticks int) {
	if position != 0 {
		return 0, 0
	}

	return honba, riichiSticks
}

// MisfitWinError reports a win settled as the other kind: a ron, chankan or houtei settled as a
// tsumo, or a tsumo, rinshan or haitei settled as a ron.
type MisfitWinError struct {
	Win score.Win
}

func (e MisfitWinError) Error() string {
	if e.Win.IsTsumo() {
		return "a tsumo win cannot be settled as a ron"
	}

	return "a ron win cannot be settled as a tsumo"
}

func RonScoreChanges(
	winner, discarder tile.Seat, payment play.Payment, honba, riichiSticks int, pao play.Option[tile.Seat],
) [tile.SeatCount]int {
	ron, ok := payment.(play.RonPayment)
	if !ok {
		panic(play.EngineFaultError{Err: MisfitPaymentError{Payment: payment}})
	}

	handPoints, honbaPoints := ron.Discarder, score.HonbaBonus(score.WinRon, honba)

	var changes [tile.SeatCount]int
	if pao.OK && pao.Value != discarder {
		liableHalf := handPoints / 2
		changes[discarder.Index()] = -(handPoints - liableHalf)
		changes[pao.Value.Index()] = -(liableHalf + honbaPoints)
	} else {
		changes[discarder.Index()] = -(handPoints + honbaPoints)
	}

	changes[winner.Index()] = handPoints + honbaPoints + score.RiichiSticksBonus(riichiSticks)
	return changes
}

// RonWin returns how a ron on a call prompt's tile with liveTiles left is won: houtei on the last
// discard, chankan on a kan's tile, else ron.
func RonWin(source play.CallSource, liveTiles int) score.Win {
	if IsHoutei(liveTiles, source) {
		return score.WinHoutei
	}

	if source == play.SourceDiscard {
		return score.WinRon
	}

	return score.WinChankan
}

// BaseSituation returns what a win is scored with besides the tiles, with no first turn, honba or
// riichi sticks.
func BaseSituation(win score.Win, seatWind, roundWind tile.Wind, riichi play.Option[play.Riichi]) score.Situation {
	return score.Situation{Win: win, Riichi: riichi, SeatWind: seatWind, RoundWind: roundWind}
}
