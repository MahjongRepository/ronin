package offer

import (
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
	counts, err := tile.KindCounts(slices.Values(append(slices.Clone(concealed), winTile)))
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

func tilesOf(ids []tile.TileID) []tile.Tile {
	tiles := make([]tile.Tile, len(ids))
	for i, id := range ids {
		tiles[i] = id.Tile(rules.AkaDora)
	}
	return tiles
}

// TsumoScoreChanges returns what a tsumo moves by seat: each payer's share of payment and its
// honba, all of it charged to a liable seat, and to the winner all of it with the riichi sticks.
// A ron payment charges no share.
func TsumoScoreChanges(
	winner, dealer tile.Seat, payment play.Payment, honba, riichiSticks int, pao play.Option[tile.Seat],
) [tile.SeatCount]int {
	honbaPerPayer := score.HonbaBonus(score.WinTsumo, honba)
	var changes [tile.SeatCount]int
	for _, payer := range tile.Seats() {
		if payer == winner {
			continue
		}

		paid := tsumoShare(payment, payer == dealer) + honbaPerPayer
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

func tsumoShare(payment play.Payment, isDealer bool) int {
	share := 0
	switch p := payment.(type) {
	case play.TsumoPayment:
		share = p.NonDealer
		if isDealer {
			share = p.Dealer
		}
	case play.DealerTsumoPayment:
		share = p.NonDealer
	case play.RonPayment:
	}
	return share
}

// RonScoreChanges returns what one ron moves by seat, honba and riichiSticks the table's when
// this winner takes them, else 0: the discarder pays the hand and the honba, but a liable seat
// other than the discarder pays half the hand and the honba. A payment other than a ron moves no
// hand points.
func RonScoreChanges(
	winner, discarder tile.Seat, payment play.Payment, honba, riichiSticks int, pao play.Option[tile.Seat],
) [tile.SeatCount]int {
	ron, _ := payment.(play.RonPayment)
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
