package engine

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Table is the round a win is settled in: the ruleset it plays under, its zero value the default
// play.RulesetTenhou; its dealer, its round wind, and the honba and riichi sticks on the table.
type Table struct {
	Ruleset      play.Ruleset
	Dealer       tile.Seat
	RoundWind    tile.Wind
	Honba        int
	RiichiSticks int
}

// WinningHand is one winner's hand to settle: the winner's seat, the concealed tiles without the
// winning tile, the winning tile, the declared melds, the dora and ura dora indicators, how the
// tile came, the winner's riichi, absent without one, whether the win comes before the winner's
// first discard with no call made, and the seat liable for the yakuman, absent without one.
type WinningHand struct {
	Seat           tile.Seat
	Concealed      []tile.TileID
	WinTile        tile.TileID
	Melds          []play.MeldView
	DoraIndicators []tile.TileID
	UraIndicators  []tile.TileID
	Win            Win
	Riichi         play.Option[play.Riichi]
	FirstTurn      bool
	Pao            play.Option[tile.Seat]
}

// Win is how the winning tile came.
type Win = score.Win

const (
	WinRon     = score.WinRon
	WinChankan = score.WinChankan
	WinHoutei  = score.WinHoutei
	WinTsumo   = score.WinTsumo
	WinRinshan = score.WinRinshan
	WinHaitei  = score.WinHaitei
)

// HandValue is the value of a winning hand's most expensive reading, scored with no honba and no
// riichi sticks.
type HandValue = score.HandValue

// SettledWin is a win as a game settles it: the hand's value and what the win moves by seat, the
// table's honba and riichi sticks included.
type SettledWin struct {
	Value        HandValue
	ScoreChanges [tile.SeatCount]int
}

// MisfitMeldError reports a meld whose tiles do not fit its kind.
type MisfitMeldError = meld.MisfitMeldError

// MisfitWinError reports a win settled as the other kind.
type MisfitWinError = offer.MisfitWinError

// SettleTsumo settles a tsumo as a game does, honba, riichi sticks and a liable seat included.
// It returns a MisfitWinError for a ron, a MisfitMeldError, or the scorer's errors.
func SettleTsumo(table Table, h WinningHand) (SettledWin, error) {
	if !h.Win.IsTsumo() {
		return SettledWin{}, MisfitWinError{Win: h.Win}
	}

	value, err := settledValue(table, h)
	if err != nil {
		return SettledWin{}, err
	}

	changes := offer.TsumoScoreChanges(
		h.Seat, table.Dealer, value.Payment, table.Honba, table.RiichiSticks, h.Pao, table.Ruleset,
	)
	return SettledWin{Value: value, ScoreChanges: changes}, nil
}

// SettleRon settles the winners of one ron on discarder's tile as a game does, in the order given,
// which a game sets from the discarder's next seat on: the first winner takes the table's honba
// and riichi sticks. It returns SettleTsumo's errors for the first winner that has one.
func SettleRon(table Table, discarder tile.Seat, winners []WinningHand) ([]SettledWin, error) {
	settled := make([]SettledWin, 0, len(winners))
	for position, h := range winners {
		if h.Win.IsTsumo() {
			return nil, MisfitWinError{Win: h.Win}
		}

		value, err := settledValue(table, h)
		if err != nil {
			return nil, err
		}

		honba, sticks := offer.RonTableShare(position, table.Honba, table.RiichiSticks)
		changes := offer.RonScoreChanges(h.Seat, discarder, value.Payment, honba, sticks, h.Pao, table.Ruleset)
		settled = append(settled, SettledWin{Value: value, ScoreChanges: changes})
	}

	return settled, nil
}

func settledValue(table Table, h WinningHand) (HandValue, error) {
	situation := offer.BaseSituation(h.Win, h.Seat.Wind(table.Dealer), table.RoundWind, h.Riichi)
	situation.FirstTurn = h.FirstTurn
	return offer.HandValue(h.Concealed, h.WinTile, offer.Scoring{
		Ruleset:        table.Ruleset,
		Situation:      situation,
		Melds:          h.Melds,
		DoraIndicators: h.DoraIndicators,
		UraIndicators:  h.UraIndicators,
	})
}
