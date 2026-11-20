package offer

import (
	"errors"
	"fmt"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Completes reports whether the concealed tiles with winTile added form a complete hand.
func Completes(concealed []tile.TileID, winTile tile.TileID) bool {
	counts, err := tile.KindCounts(append(slices.Clone(concealed), winTile))
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

// HandValue returns the value of concealed, the winning tile not among them, won on winTile,
// scored with no honba and no riichi sticks: score.EstimateHandValue's errors, or a
// meld.MisfitMeldError for the first meld that does not fit its kind.
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

// OfferedValue returns HandValue's value of a win the seat may be offered, and false when the
// hand has no yaku. It panics with a play.EngineFaultError on any other scorer error, since the
// hand already completes.
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

// MisfitPaymentError reports a payment whose variant does not fit the win it pays: a ron payment
// for a tsumo or a tsumo payment for a ron, or a dealer's tsumo payment to a non-dealer and the
// reverse.
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

// TsumoScoreChanges returns what a tsumo moves by seat: each payer's share of payment and its
// honba, all of it charged to a liable seat, and to the winner all of it with the riichi sticks.
// It panics with a play.EngineFaultError wrapping a MisfitPaymentError when payment is a ron
// payment, or a dealer's tsumo payment and the winner is not the dealer, or the reverse.
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

// RonScoreChanges returns what one ron moves by seat, honba and riichiSticks the table's when
// this winner takes them, else 0: the discarder pays the hand and the honba, but a liable seat
// other than the discarder pays half the hand and the honba. It panics with a
// play.EngineFaultError wrapping a MisfitPaymentError when payment is not a ron payment.
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
