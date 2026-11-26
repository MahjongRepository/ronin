package score

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	manganBase          = 2000
	hanemanBase         = 3000
	baimanBase          = 4000
	sanbaimanBase       = 6000
	yakumanBase         = 8000
	paymentRounding     = 100
	manganHan           = 5
	hanemanHan          = 6
	baimanHan           = 8
	sanbaimanHan        = 11
	kazoeHan            = 13
	basePointsHanOffset = 2
)

// HonbaBonus returns what each payer of a win adds for honba repeat counters: 300 each on a ron,
// 100 each on a tsumo.
func HonbaBonus(win Win, honba int) int {
	if win.IsTsumo() {
		return honba * rules.HonbaTsumoBonusPerLoser
	}

	return honba * rules.HonbaRonBonus
}

// RiichiSticksBonus returns what riichiSticks pay the winner who takes them: 1000 each.
func RiichiSticksBonus(riichiSticks int) int {
	return riichiSticks * rules.RiichiStickValue
}

func NagashiMangan(seatWind tile.Wind) play.Payment {
	shares := sharesOf(manganBase)
	if seatWind == tile.East {
		return play.DealerTsumoPayment{NonDealer: shares.double}
	}

	return play.TsumoPayment{Dealer: shares.double, NonDealer: shares.single}
}

type shares struct {
	single    int
	double    int
	quadruple int
	sextuple  int
}

func sharesOf(rounded int) shares {
	return shares{single: rounded, double: 2 * rounded, quadruple: 4 * rounded, sextuple: 6 * rounded}
}

func paymentOf(value play.Value, win Win, seatWind tile.Wind, honba int, rules Rules) (
	play.Option[play.Limit], play.Payment,
) {
	limit, paid := limitAndShares(value, rules)
	bonus := HonbaBonus(win, honba)
	isDealer := seatWind == tile.East
	switch {
	case win.IsTsumo() && isDealer:
		return limit, play.DealerTsumoPayment{NonDealer: paid.double + bonus}
	case win.IsTsumo():
		return limit, play.TsumoPayment{Dealer: paid.double + bonus, NonDealer: paid.single + bonus}
	case isDealer:
		return limit, play.RonPayment{Discarder: paid.sextuple + bonus}
	default:
		return limit, play.RonPayment{Discarder: paid.quadruple + bonus}
	}
}

func limitAndShares(value play.Value, rules Rules) (play.Option[play.Limit], shares) {
	var limit play.Option[play.Limit]
	var paid shares
	switch v := value.(type) {
	case play.Han:
		limit, paid = hanShares(v, rules)
	case play.Yakuman:
		limit, paid = play.Some(play.LimitYakuman), sharesOf(yakumanBase*v.Count)
	}

	return limit, paid
}

func hanShares(value play.Han, rules Rules) (play.Option[play.Limit], shares) {
	if value.Han < manganHan {
		return hanFuShares(value.Han, value.Fu, rules)
	}

	limit, rounded := limitTier(value.Han)
	return play.Some(limit), sharesOf(rounded)
}

func limitTier(han int) (play.Limit, int) {
	switch {
	case han >= kazoeHan:
		return play.LimitYakuman, yakumanBase
	case han >= sanbaimanHan:
		return play.LimitSanbaiman, sanbaimanBase
	case han >= baimanHan:
		return play.LimitBaiman, baimanBase
	case han >= hanemanHan:
		return play.LimitHaneman, hanemanBase
	default:
		return play.LimitMangan, manganBase
	}
}

func hanFuShares(han, fu int, rules Rules) (play.Option[play.Limit], shares) {
	basePoints := fu << (basePointsHanOffset + han)
	single := nextMultipleOf(basePoints, paymentRounding)
	isKiriage := rules.Kiriage && ((han == 4 && fu == 30) || (han == 3 && fu == 60))
	if single > manganBase || isKiriage {
		return play.Some(play.LimitMangan), sharesOf(manganBase)
	}

	return play.Option[play.Limit]{}, shares{
		single:    single,
		double:    nextMultipleOf(2*basePoints, paymentRounding),
		quadruple: nextMultipleOf(4*basePoints, paymentRounding),
		sextuple:  nextMultipleOf(6*basePoints, paymentRounding),
	}
}
