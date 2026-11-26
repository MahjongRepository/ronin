package play_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

func TestLimitString_ShouldNameEachLimit(t *testing.T) {
	for limit, want := range map[play.Limit]string{
		play.LimitMangan:    "mangan",
		play.LimitHaneman:   "haneman",
		play.LimitBaiman:    "baiman",
		play.LimitSanbaiman: "sanbaiman",
		play.LimitYakuman:   "yakuman",
		play.Limit(5):       "play.Limit(5)",
	} {
		if got := limit.String(); got != want {
			t.Errorf("Limit(%d).String = %q, want %q", limit, got, want)
		}
	}
}

func TestValueString_ShouldShowHanAndFuOrTheYakumanCount(t *testing.T) {
	for _, c := range []struct {
		name  string
		value play.Value
		want  string
	}{
		{name: "han and fu", value: play.Han{Han: 3, Fu: 30}, want: "3 han, 30 fu"},
		{name: "single yakuman", value: play.Yakuman{Count: 1, Fu: play.Some(40)}, want: "yakuman"},
		{name: "double yakuman", value: play.Yakuman{Count: 2}, want: "2x yakuman"},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.value.String(); got != c.want {
				t.Errorf("String = %q, want %q", got, c.want)
			}
		})
	}
}

func TestPaymentSum_ShouldAddWhatEveryPayerPays(t *testing.T) {
	for _, c := range []struct {
		name    string
		payment play.Payment
		want    int
	}{
		{name: "ron", payment: play.RonPayment{Discarder: 7700}, want: 7700},
		{name: "tsumo", payment: play.TsumoPayment{Dealer: 3900, NonDealer: 2000}, want: 7900},
		{name: "dealer tsumo", payment: play.DealerTsumoPayment{NonDealer: 4000}, want: 12000},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.payment.Sum(); got != c.want {
				t.Errorf("%#v Sum = %d, want %d", c.payment, got, c.want)
			}
		})
	}
}
