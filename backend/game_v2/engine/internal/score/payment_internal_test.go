package score

import (
	"math"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type paymentCase struct {
	value   play.Value
	limit   play.Option[play.Limit]
	payment play.Payment
}

func checkPayments(t *testing.T, win Win, seatWind tile.Wind, rules Rules, cases []paymentCase) {
	t.Helper()
	for _, c := range cases {
		limit, payment := paymentOf(c.value, win, seatWind, 0, rules)
		if limit != c.limit || payment != c.payment {
			t.Errorf("paymentOf(%v, %v, %v) = %v, %+v; want %v, %+v", c.value, win, seatWind, limit, payment,
				c.limit, c.payment)
		}
	}
}

func noLimit() play.Option[play.Limit] {
	return play.Option[play.Limit]{}
}

func yakumanTimes(count int) play.Yakuman {
	return play.Yakuman{Count: count}
}

func TestPaymentOf_WhenANonDealerWinsByRon_ShouldChargeTheDiscarderFourShares(t *testing.T) {
	yakuman := play.Some(play.LimitYakuman)
	checkPayments(t, WinRon, tile.South, defaultRules(), []paymentCase{
		{play.Han{Han: 1, Fu: 30}, noLimit(), play.RonPayment{Discarder: 1000}},
		{play.Han{Han: 1, Fu: 110}, noLimit(), play.RonPayment{Discarder: 3600}},
		{play.Han{Han: 2, Fu: 30}, noLimit(), play.RonPayment{Discarder: 2000}},
		{play.Han{Han: 3, Fu: 30}, noLimit(), play.RonPayment{Discarder: 3900}},
		{play.Han{Han: 4, Fu: 30}, noLimit(), play.RonPayment{Discarder: 7700}},
		{play.Han{Han: 4, Fu: 40}, play.Some(play.LimitMangan), play.RonPayment{Discarder: 8000}},
		{play.Han{Han: 5}, play.Some(play.LimitMangan), play.RonPayment{Discarder: 8000}},
		{play.Han{Han: 6}, play.Some(play.LimitHaneman), play.RonPayment{Discarder: 12000}},
		{play.Han{Han: 8}, play.Some(play.LimitBaiman), play.RonPayment{Discarder: 16000}},
		{play.Han{Han: 11}, play.Some(play.LimitSanbaiman), play.RonPayment{Discarder: 24000}},
		{yakumanTimes(1), yakuman, play.RonPayment{Discarder: 32000}},
		{yakumanTimes(2), yakuman, play.RonPayment{Discarder: 64000}},
		{yakumanTimes(3), yakuman, play.RonPayment{Discarder: 96000}},
		{yakumanTimes(4), yakuman, play.RonPayment{Discarder: 128000}},
		{yakumanTimes(5), yakuman, play.RonPayment{Discarder: 160000}},
		{yakumanTimes(6), yakuman, play.RonPayment{Discarder: 192000}},
	})
}

func TestPaymentOf_WhenTheDealerWinsByRon_ShouldChargeTheDiscarderSixShares(t *testing.T) {
	yakuman := play.Some(play.LimitYakuman)
	checkPayments(t, WinRon, tile.East, defaultRules(), []paymentCase{
		{play.Han{Han: 1, Fu: 30}, noLimit(), play.RonPayment{Discarder: 1500}},
		{play.Han{Han: 2, Fu: 30}, noLimit(), play.RonPayment{Discarder: 2900}},
		{play.Han{Han: 3, Fu: 30}, noLimit(), play.RonPayment{Discarder: 5800}},
		{play.Han{Han: 4, Fu: 30}, noLimit(), play.RonPayment{Discarder: 11600}},
		{play.Han{Han: 5}, play.Some(play.LimitMangan), play.RonPayment{Discarder: 12000}},
		{play.Han{Han: 6}, play.Some(play.LimitHaneman), play.RonPayment{Discarder: 18000}},
		{play.Han{Han: 8}, play.Some(play.LimitBaiman), play.RonPayment{Discarder: 24000}},
		{play.Han{Han: 11}, play.Some(play.LimitSanbaiman), play.RonPayment{Discarder: 36000}},
		{yakumanTimes(1), yakuman, play.RonPayment{Discarder: 48000}},
		{yakumanTimes(2), yakuman, play.RonPayment{Discarder: 96000}},
		{yakumanTimes(3), yakuman, play.RonPayment{Discarder: 144000}},
		{yakumanTimes(4), yakuman, play.RonPayment{Discarder: 192000}},
		{yakumanTimes(5), yakuman, play.RonPayment{Discarder: 240000}},
		{yakumanTimes(6), yakuman, play.RonPayment{Discarder: 288000}},
	})
}

func TestPaymentOf_WhenANonDealerWinsByTsumo_ShouldChargeTheDealerDouble(t *testing.T) {
	yakuman := play.Some(play.LimitYakuman)
	checkPayments(t, WinTsumo, tile.South, defaultRules(), []paymentCase{
		{play.Han{Han: 1, Fu: 30}, noLimit(), play.TsumoPayment{Dealer: 500, NonDealer: 300}},
		{play.Han{Han: 3, Fu: 30}, noLimit(), play.TsumoPayment{Dealer: 2000, NonDealer: 1000}},
		{play.Han{Han: 3, Fu: 60}, noLimit(), play.TsumoPayment{Dealer: 3900, NonDealer: 2000}},
		{play.Han{Han: 4, Fu: 30}, noLimit(), play.TsumoPayment{Dealer: 3900, NonDealer: 2000}},
		{play.Han{Han: 5}, play.Some(play.LimitMangan), play.TsumoPayment{Dealer: 4000, NonDealer: 2000}},
		{play.Han{Han: 6}, play.Some(play.LimitHaneman), play.TsumoPayment{Dealer: 6000, NonDealer: 3000}},
		{play.Han{Han: 8}, play.Some(play.LimitBaiman), play.TsumoPayment{Dealer: 8000, NonDealer: 4000}},
		{play.Han{Han: 11}, play.Some(play.LimitSanbaiman), play.TsumoPayment{Dealer: 12000, NonDealer: 6000}},
		{yakumanTimes(1), yakuman, play.TsumoPayment{Dealer: 16000, NonDealer: 8000}},
		{yakumanTimes(2), yakuman, play.TsumoPayment{Dealer: 32000, NonDealer: 16000}},
		{yakumanTimes(3), yakuman, play.TsumoPayment{Dealer: 48000, NonDealer: 24000}},
		{yakumanTimes(4), yakuman, play.TsumoPayment{Dealer: 64000, NonDealer: 32000}},
		{yakumanTimes(5), yakuman, play.TsumoPayment{Dealer: 80000, NonDealer: 40000}},
		{yakumanTimes(6), yakuman, play.TsumoPayment{Dealer: 96000, NonDealer: 48000}},
	})
}

func TestPaymentOf_WhenTheDealerWinsByTsumo_ShouldChargeEveryoneDouble(t *testing.T) {
	yakuman := play.Some(play.LimitYakuman)
	checkPayments(t, WinTsumo, tile.East, defaultRules(), []paymentCase{
		{play.Han{Han: 1, Fu: 30}, noLimit(), play.DealerTsumoPayment{NonDealer: 500}},
		{play.Han{Han: 3, Fu: 30}, noLimit(), play.DealerTsumoPayment{NonDealer: 2000}},
		{play.Han{Han: 4, Fu: 30}, noLimit(), play.DealerTsumoPayment{NonDealer: 3900}},
		{play.Han{Han: 5}, play.Some(play.LimitMangan), play.DealerTsumoPayment{NonDealer: 4000}},
		{play.Han{Han: 6}, play.Some(play.LimitHaneman), play.DealerTsumoPayment{NonDealer: 6000}},
		{play.Han{Han: 8}, play.Some(play.LimitBaiman), play.DealerTsumoPayment{NonDealer: 8000}},
		{play.Han{Han: 11}, play.Some(play.LimitSanbaiman), play.DealerTsumoPayment{NonDealer: 12000}},
		{yakumanTimes(1), yakuman, play.DealerTsumoPayment{NonDealer: 16000}},
		{yakumanTimes(2), yakuman, play.DealerTsumoPayment{NonDealer: 32000}},
		{yakumanTimes(3), yakuman, play.DealerTsumoPayment{NonDealer: 48000}},
		{yakumanTimes(4), yakuman, play.DealerTsumoPayment{NonDealer: 64000}},
		{yakumanTimes(5), yakuman, play.DealerTsumoPayment{NonDealer: 80000}},
		{yakumanTimes(6), yakuman, play.DealerTsumoPayment{NonDealer: 96000}},
	})
}

func TestPaymentOf_WhenWonOnAnyTsumoOrRonKind_ShouldPayAsThatKind(t *testing.T) {
	oneHan := []paymentCase{{play.Han{Han: 1, Fu: 30}, noLimit(), play.TsumoPayment{Dealer: 500, NonDealer: 300}}}
	for _, win := range []Win{WinTsumo, WinRinshan, WinHaitei} {
		checkPayments(t, win, tile.South, defaultRules(), oneHan)
	}

	oneHan = []paymentCase{{play.Han{Han: 1, Fu: 30}, noLimit(), play.RonPayment{Discarder: 1000}}}
	for _, win := range []Win{WinRon, WinChankan, WinHoutei} {
		checkPayments(t, win, tile.South, defaultRules(), oneHan)
	}
}

func TestPaymentOf_WhenHonbaAreOnTheTable_ShouldAddThemToEveryPayer(t *testing.T) {
	for _, tc := range []struct {
		value    play.Value
		win      Win
		seatWind tile.Wind
		honba    int
		limit    play.Option[play.Limit]
		payment  play.Payment
		sum      int
	}{
		{play.Han{Han: 3, Fu: 30}, WinTsumo, tile.East, 2, noLimit(), play.DealerTsumoPayment{NonDealer: 2200}, 6600},
		{
			play.Han{Han: 4, Fu: 30},
			WinTsumo, tile.West, 4, noLimit(),
			play.TsumoPayment{Dealer: 4300, NonDealer: 2400},
			9100,
		},
		{
			play.Han{Han: 6, Fu: 30},
			WinRon, tile.West, 5, play.Some(play.LimitHaneman),
			play.RonPayment{Discarder: 13500},
			13500,
		},
		{
			play.Han{Han: 5, Fu: 30},
			WinRon, tile.East, 5, play.Some(play.LimitMangan),
			play.RonPayment{Discarder: 13500},
			13500,
		},
	} {
		limit, payment := paymentOf(tc.value, tc.win, tc.seatWind, tc.honba, defaultRules())
		if limit != tc.limit || payment != tc.payment || payment.Sum() != tc.sum {
			t.Errorf("paymentOf(%v, honba %d) = %v, %+v (sum %d); want %v, %+v (sum %d)", tc.value, tc.honba, limit,
				payment, payment.Sum(), tc.limit, tc.payment, tc.sum)
		}
	}
}

func TestPaymentOf_WhenKiriage_ShouldRoundFourHan30FuAndThreeHan60FuUpToMangan(t *testing.T) {
	rules := defaultRules()
	rules.Kiriage = true
	mangan := play.Some(play.LimitMangan)
	checkPayments(t, WinRon, tile.South, rules, []paymentCase{
		{play.Han{Han: 4, Fu: 30}, mangan, play.RonPayment{Discarder: 8000}},
		{play.Han{Han: 3, Fu: 60}, mangan, play.RonPayment{Discarder: 8000}},
		{play.Han{Han: 4, Fu: 40}, mangan, play.RonPayment{Discarder: 8000}},
		{play.Han{Han: 3, Fu: 50}, noLimit(), play.RonPayment{Discarder: 6400}},
	})
	checkPayments(t, WinRon, tile.East, rules, []paymentCase{
		{play.Han{Han: 4, Fu: 30}, mangan, play.RonPayment{Discarder: 12000}},
		{play.Han{Han: 3, Fu: 60}, mangan, play.RonPayment{Discarder: 12000}},
	})
}

func TestPaymentOf_WhenThirteenHanOrMore_ShouldPayASingleYakuman(t *testing.T) {
	yakuman := play.Some(play.LimitYakuman)
	checkPayments(t, WinRon, tile.South, defaultRules(), []paymentCase{
		{play.Han{Han: 13, Fu: 40}, yakuman, play.RonPayment{Discarder: 32000}},
		{play.Han{Han: 26, Fu: 40}, yakuman, play.RonPayment{Discarder: 32000}},
		{yakumanTimes(2), yakuman, play.RonPayment{Discarder: 64000}},
	})
}

func TestPaymentOf_WhenHanOrFuAreHuge_ShouldStayAtTheirLimit(t *testing.T) {
	checkPayments(t, WinRon, tile.South, defaultRules(), []paymentCase{
		{play.Han{Han: math.MaxUint32}, play.Some(play.LimitYakuman), play.RonPayment{Discarder: 32000}},
		{play.Han{Han: 4, Fu: math.MaxUint32}, play.Some(play.LimitMangan), play.RonPayment{Discarder: 8000}},
	})
}

func TestHonbaBonus_ShouldPay300PerHonbaOnRonAnd100PerPayerOnTsumo(t *testing.T) {
	for _, tc := range []struct {
		win  Win
		want int
	}{
		{WinRon, 900}, {WinChankan, 900}, {WinHoutei, 900}, {WinTsumo, 300}, {WinRinshan, 300}, {WinHaitei, 300},
	} {
		if got := HonbaBonus(tc.win, 3); got != tc.want {
			t.Errorf("HonbaBonus(%v, 3) = %d, want %d", tc.win, got, tc.want)
		}
	}
	if got := HonbaBonus(WinRon, 0); got != 0 {
		t.Errorf("HonbaBonus(WinRon, 0) = %d, want 0", got)
	}
}

func TestHonbaBonus_ShouldMatchWhatHonbaAddToAPayment(t *testing.T) {
	value := play.Han{Han: 2, Fu: 30}
	for _, tc := range []struct {
		win      Win
		seatWind tile.Wind
		payers   int
	}{{WinRon, tile.South, 1}, {WinTsumo, tile.South, 3}, {WinTsumo, tile.East, 3}} {
		_, without := paymentOf(value, tc.win, tc.seatWind, 0, defaultRules())
		_, with := paymentOf(value, tc.win, tc.seatWind, 2, defaultRules())

		if got, want := with.Sum()-without.Sum(), tc.payers*HonbaBonus(tc.win, 2); got != want {
			t.Errorf("2 honba add %d to a %v by %v, want %d", got, tc.win, tc.seatWind, want)
		}
	}
}

func TestRiichiSticksBonus_ShouldPay1000PerStick(t *testing.T) {
	for _, tc := range []struct{ sticks, want int }{{0, 0}, {2, 2000}} {
		if got := RiichiSticksBonus(tc.sticks); got != tc.want {
			t.Errorf("RiichiSticksBonus(%d) = %d, want %d", tc.sticks, got, tc.want)
		}
	}
}
