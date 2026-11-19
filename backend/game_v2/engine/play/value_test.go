package play_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

func TestLimitFromTenhouCode_WhenCodeIsZeroToFive_ShouldRoundTripTheLimits(t *testing.T) {
	below, err := play.LimitFromTenhouCode(0)
	if err != nil || below.OK {
		t.Errorf("LimitFromTenhouCode(0) = %v, %v, want absent", below, err)
	}

	for code, want := range []play.Limit{
		play.LimitMangan, play.LimitHaneman, play.LimitBaiman, play.LimitSanbaiman, play.LimitYakuman,
	} {
		got, err := play.LimitFromTenhouCode(code + 1)
		if err != nil || got != play.Some(want) {
			t.Errorf("LimitFromTenhouCode(%d) = %v, %v, want %s", code+1, got, err, want)
		}
		if want.TenhouCode() != code+1 {
			t.Errorf("%s TenhouCode = %d, want %d", want, want.TenhouCode(), code+1)
		}
	}
}

func TestLimitFromTenhouCode_WhenCodeIsPastFive_ShouldReportTheCode(t *testing.T) {
	for _, code := range []int{-1, 6} {
		_, err := play.LimitFromTenhouCode(code)
		if !errors.Is(err, play.UnknownLimitCodeError{Code: code}) {
			t.Errorf("LimitFromTenhouCode(%d) error = %v, want UnknownLimitCodeError", code, err)
		}
	}
	if got, want := (play.UnknownLimitCodeError{Code: 6}).Error(), "no Tenhou limit has code 6"; got != want {
		t.Errorf("Error = %q, want %q", got, want)
	}
}

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
