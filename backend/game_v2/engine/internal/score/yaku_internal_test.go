package score

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

type yakuHanResult struct {
	han int
	ok  bool
}

func hanOf(in yakuInput, id play.YakuID) yakuHanResult {
	han, ok := in.han(id)
	return yakuHanResult{han: han, ok: ok}
}

func openHand(rules Rules) yakuInput {
	return yakuInput{open: true, rules: rules}
}

func closedHand(rules Rules) yakuInput {
	return yakuInput{rules: rules}
}

func TestYakuHan_WhenAClosedOnlyYakuIsOpen_ShouldRefuseIt(t *testing.T) {
	if got := hanOf(openHand(defaultRules()), play.YakuRiichi); got.ok {
		t.Errorf("yakuHan(riichi, open) = %v, want refused", got)
	}
}

func TestYakuHan_WhenTanyaoIsOpen_ShouldNeedKuitan(t *testing.T) {
	kuitan := defaultRules()
	kuitan.OpenTanyao = true
	if got := hanOf(openHand(defaultRules()), play.YakuTanyao); got.ok {
		t.Errorf("yakuHan(tanyao, open, no kuitan) = %v, want refused", got)
	}
	if got := hanOf(openHand(kuitan), play.YakuTanyao); got != (yakuHanResult{1, true}) {
		t.Errorf("yakuHan(tanyao, open, kuitan) = %v, want 1 han", got)
	}
}

func TestYakuHan_WhenAClosedOnlyDoubleFormIsOpenWithoutDoubleYakuman_ShouldRefuseIt(t *testing.T) {
	rules := defaultRules()
	rules.DoubleYakuman = false
	if got := hanOf(openHand(rules), play.YakuSuuankouTanki); got.ok {
		t.Errorf("yakuHan(suuankou tanki, open) = %v, want refused", got)
	}
}

func TestYakuHan_WhenTheHandIsClosed_ShouldCountClosedHan(t *testing.T) {
	for _, id := range play.AllYaku() {
		t.Run(id.Name(), func(t *testing.T) {
			if got := hanOf(closedHand(defaultRules()), id); got != (yakuHanResult{id.HanClosed(), true}) {
				t.Errorf("yakuHan(%s, closed) = %v, want %d han", id.Name(), got, id.HanClosed())
			}
		})
	}
}

func TestYakuHan_WhenTheHandIsOpen_ShouldCountOpenHan(t *testing.T) {
	for _, tc := range []struct {
		id     play.YakuID
		open   int
		closed int
	}{
		{play.YakuChinitsu, 5, 6},
		{play.YakuSanshoku, 1, 2},
		{play.YakuToitoi, 2, 2},
		{play.YakuDaisuushii, 26, 26},
	} {
		t.Run(tc.id.Name(), func(t *testing.T) {
			if got := hanOf(openHand(defaultRules()), tc.id); got != (yakuHanResult{tc.open, true}) {
				t.Errorf("yakuHan(%s, open) = %v, want %d han", tc.id.Name(), got, tc.open)
			}
			if got := hanOf(closedHand(defaultRules()), tc.id); got != (yakuHanResult{tc.closed, true}) {
				t.Errorf("yakuHan(%s, closed) = %v, want %d han", tc.id.Name(), got, tc.closed)
			}
		})
	}
}

func TestYakuHan_WhenDoubleYakumanIsOff_ShouldCountTheDoubleFormsThirteen(t *testing.T) {
	rules := defaultRules()
	rules.DoubleYakuman = false
	for _, id := range []play.YakuID{
		play.YakuDaburuKokushiMusou, play.YakuSuuankouTanki, play.YakuDaburuChuurenPoutou, play.YakuDaisuushii,
	} {
		t.Run("closed "+id.Name(), func(t *testing.T) {
			if got := hanOf(closedHand(rules), id); got != (yakuHanResult{13, true}) {
				t.Errorf("yakuHan(%s, closed) = %v, want 13 han", id.Name(), got)
			}
		})
	}
	for _, id := range []play.YakuID{play.YakuDaisuushii, play.YakuDaisangen} {
		t.Run("open "+id.Name(), func(t *testing.T) {
			if got := hanOf(openHand(rules), id); got != (yakuHanResult{13, true}) {
				t.Errorf("yakuHan(%s, open) = %v, want 13 han", id.Name(), got)
			}
		})
	}
}
