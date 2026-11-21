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
			t.Errorf("String = %q, want %q", got, want)
		}
	}
}

func TestValueString_ShouldShowHanAndFuOrTheYakumanCount(t *testing.T) {
	for _, c := range []struct {
		value play.Value
		want  string
	}{
		{play.Han{Han: 3, Fu: 30}, "3 han, 30 fu"},
		{play.Yakuman{Count: 1, Fu: play.Some(40)}, "yakuman"},
		{play.Yakuman{Count: 2}, "2x yakuman"},
	} {
		if got := c.value.String(); got != c.want {
			t.Errorf("String = %q, want %q", got, c.want)
		}
	}
}

func TestPaymentSum_ShouldAddWhatEveryPayerPays(t *testing.T) {
	for _, c := range []struct {
		payment play.Payment
		want    int
	}{
		{play.RonPayment{Discarder: 7700}, 7700},
		{play.TsumoPayment{Dealer: 3900, NonDealer: 2000}, 7900},
		{play.DealerTsumoPayment{NonDealer: 4000}, 12000},
	} {
		if got := c.payment.Sum(); got != c.want {
			t.Errorf("%#v Sum = %d, want %d", c.payment, got, c.want)
		}
	}
}
