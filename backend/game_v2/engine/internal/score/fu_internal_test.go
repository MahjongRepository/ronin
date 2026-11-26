package score

import (
	"fmt"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type fuCase struct {
	concealed string
	winTile   string
	win       Win
	rules     Rules
	valued    []tile.Kind
	melds     []meld.Meld
}

type fuResult struct {
	details []FuDetail
	fu      int
}

func wonReading(t *testing.T, concealed, winTile string, melds []meld.Meld) (hand.Reading, []hand.WinBlock) {
	t.Helper()
	decomposition := decompositionOf(t, concealed+winTile, 0)
	blocks := slices.Collect(decomposition.WinBlocks(kindOf(t, winTile)))
	return decomposition.Reading(hand.MeldSetsOf(melds)), blocks
}

func valuedKindsOf(kinds []tile.Kind) [valuedKinds]tile.Kind {
	valued := [valuedKinds]tile.Kind{tile.KindCount, tile.KindCount, tile.KindCount, tile.KindCount, tile.KindCount}
	copy(valued[:], kinds)
	return valued
}

func fuOf(t *testing.T, c fuCase) fuResult {
	t.Helper()
	reading, blocks := wonReading(t, c.concealed, c.winTile, c.melds)
	details, fu := calculateFu(fuInput{
		reading:  reading,
		winBlock: blocks[0],
		win:      kindOf(t, c.winTile),
		tsumo:    c.win.IsTsumo(),
		rules:    c.rules,
		valued:   valuedKindsOf(c.valued),
		open:     slices.ContainsFunc(c.melds, meld.Meld.IsOpen),
	})
	return fuResult{details: slices.Clone(details.all()), fu: fu}
}

func checkFu(t *testing.T, c fuCase, want fuResult) {
	t.Helper()
	got := fuOf(t, c)
	if !slices.Equal(got.details, want.details) || got.fu != want.fu {
		t.Errorf("calculateFu(%s + %s) = %v, %d; want %v, %d", c.concealed, c.winTile, got.details, got.fu,
			want.details, want.fu)
	}
}

func TestCalculateFu_WhenSevenPairs_ShouldScoreChiitoitsuAt25(t *testing.T) {
	checkFu(t, fuCase{concealed: "115599m6p112244s", winTile: "6p", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 25, Reason: FuBase}}, 25})
}

func TestCalculateFu_WhenOpenHandWithAPon_ShouldScoreTheOpenBase(t *testing.T) {
	melds := []meld.Meld{newMeld(t, meld.Pon, "222s")}
	checkFu(t, fuCase{concealed: "123456m11p78s", winTile: "6s", win: WinRon, rules: defaultRules(), melds: melds},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuOpenPon}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenWonOnEitherBlock_ShouldScoreThatBlock(t *testing.T) {
	reading, blocks := wonReading(t, "234789m1234566p", "6p", nil)
	win := kindOf(t, "6p")
	for _, tc := range []struct {
		block hand.WinBlock
		want  int
	}{{blocks[0], 30}, {blocks[1], 40}} {
		t.Run(fmt.Sprint(tc.want), func(t *testing.T) {
			_, fu := calculateFu(fuInput{reading: reading, winBlock: tc.block, win: win, rules: defaultRules()})
			if fu != tc.want {
				t.Errorf("calculateFu(block %v) = %d, want %d", tc.block, fu, tc.want)
			}
		})
	}
}

func TestCalculateFu_WhenOpenPinfuShapeByRon_ShouldAddHandWithoutFu(t *testing.T) {
	melds := []meld.Meld{newMeld(t, meld.Chi, "234s")}
	checkFu(t, fuCase{concealed: "234567m22p78s", winTile: "6s", win: WinRon, rules: defaultRules(), melds: melds},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuHandWithoutFu}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenOpenPinfuShapeByTsumo_ShouldAddTsumoFuWhateverTheOpenPinfuRule(t *testing.T) {
	melds := []meld.Meld{newMeld(t, meld.Chi, "234s")}
	for _, fuForOpenPinfu := range []bool{true, false} {
		t.Run(fmt.Sprintf("FuForOpenPinfu=%t", fuForOpenPinfu), func(t *testing.T) {
			rules := defaultRules()
			rules.FuForOpenPinfu = fuForOpenPinfu
			checkFu(t, fuCase{concealed: "234567m22p78s", winTile: "6s", win: WinTsumo, rules: rules, melds: melds},
				fuResult{[]FuDetail{{Fu: 2, Reason: FuTsumo}, {Fu: 20, Reason: FuBase}}, 30})
		})
	}
}

func TestCalculateFu_WhenOpenPinfuShapeByRonWithoutTheOpenPinfuRule_ShouldScore20(t *testing.T) {
	melds := []meld.Meld{newMeld(t, meld.Chi, "234s")}
	rules := defaultRules()
	rules.FuForOpenPinfu = false
	checkFu(t, fuCase{concealed: "234567m22p78s", winTile: "6s", win: WinRon, rules: rules, melds: melds},
		fuResult{[]FuDetail{{Fu: 20, Reason: FuBase}}, 20})
}

func TestCalculateFu_WhenClosedTsumoWithAPon_ShouldAddTsumoFu(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m11p22278s", winTile: "6s", win: WinTsumo, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 4, Reason: FuClosedPon}, {Fu: 2, Reason: FuTsumo}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenPinfuTsumo_ShouldScore20(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m123p2278s", winTile: "6s", win: WinTsumo, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 20, Reason: FuBase}}, 20})
}

func TestCalculateFu_WhenPinfuTsumoUnderThePinfuTsumoFuRule_ShouldAddTsumoFu(t *testing.T) {
	rules := defaultRules()
	rules.FuForPinfuTsumo = true
	checkFu(t, fuCase{concealed: "123456m123p2278s", winTile: "6s", win: WinTsumo, rules: rules},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuTsumo}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenClosedTsumoWithATerminalPon_ShouldAddTsumoFu(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m111p2278s", winTile: "6s", win: WinTsumo, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 8, Reason: FuClosedTerminalPon}, {Fu: 2, Reason: FuTsumo}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenAConcealedCopyOfAChiMeldIsWonOnTheMiddle_ShouldKeepKanchanFu(t *testing.T) {
	melds := []meld.Meld{newMeld(t, meld.Chi, "234s")}
	checkFu(t, fuCase{concealed: "123456m55p24s", winTile: "3s", win: WinRon, rules: defaultRules(), melds: melds},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuKanchan}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenWonOnAnEdgeWait_ShouldAddPenchanFu(t *testing.T) {
	for _, tc := range []struct{ concealed, winTile string }{{"123456m12456s55p", "3s"}, {"123456m34589s55p", "7s"}} {
		t.Run(tc.winTile, func(t *testing.T) {
			checkFu(t, fuCase{concealed: tc.concealed, winTile: tc.winTile, win: WinRon, rules: defaultRules()},
				fuResult{[]FuDetail{{Fu: 2, Reason: FuPenchan}, {Fu: 30, Reason: FuBase}}, 40})
		})
	}
}

func TestCalculateFu_WhenWonOnAClosedWait_ShouldAddKanchanFu(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m55p12357s", winTile: "6s", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuKanchan}, {Fu: 30, Reason: FuBase}}, 40})
}

func TestCalculateFu_WhenThePairIsValuedOnceOrTwice_ShouldAdd2OrTheDoubleWindPairFu(t *testing.T) {
	twoFuDoubleWind := defaultRules()
	twoFuDoubleWind.FuForDoubleWindPair = 2
	for _, tc := range []struct {
		name   string
		valued []tile.Kind
		rules  Rules
		want   FuDetail
	}{
		{"valued once", []tile.Kind{tile.KindEast}, defaultRules(), FuDetail{Fu: 2, Reason: FuValuedPair}},
		{"valued twice", []tile.Kind{tile.KindEast, tile.KindEast}, defaultRules(), FuDetail{Fu: 4, Reason: FuDoubleValuedPair}},
		{
			"valued twice at 2 fu",
			[]tile.Kind{tile.KindEast, tile.KindEast},
			twoFuDoubleWind,
			FuDetail{Fu: 2, Reason: FuDoubleValuedPair},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			checkFu(t, fuCase{concealed: "123456m12378s11z", winTile: "6s", win: WinRon, rules: tc.rules, valued: tc.valued},
				fuResult{[]FuDetail{tc.want, {Fu: 30, Reason: FuBase}}, 40})
		})
	}
}

func TestCalculateFu_WhenWonOnThePair_ShouldAddPairWaitFu(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m1p123678s", winTile: "1p", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuPairWait}, {Fu: 30, Reason: FuBase}}, 40})
}

func TestCalculateFu_WhenAConcealedPonOfSimples_ShouldScoreItClosedUnlessARonCompletesIt(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m11p22278s", winTile: "6s", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 4, Reason: FuClosedPon}, {Fu: 30, Reason: FuBase}}, 40})
	checkFu(t, fuCase{concealed: "123456m11p22678s", winTile: "2s", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 2, Reason: FuOpenPon}, {Fu: 30, Reason: FuBase}}, 40})
}

func TestCalculateFu_WhenAConcealedPonOfTerminals_ShouldScoreItClosedUnlessARonCompletesIt(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m11p11178s", winTile: "6s", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 8, Reason: FuClosedTerminalPon}, {Fu: 30, Reason: FuBase}}, 40})
	checkFu(t, fuCase{concealed: "123456m11p11678s", winTile: "1s", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 4, Reason: FuOpenTerminalPon}, {Fu: 30, Reason: FuBase}}, 40})
}

func TestCalculateFu_WhenAConcealedPonOfHonors_ShouldScoreItClosedUnlessARonCompletesIt(t *testing.T) {
	checkFu(t, fuCase{concealed: "123456m1178s111z", winTile: "6s", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 8, Reason: FuClosedTerminalPon}, {Fu: 30, Reason: FuBase}}, 40})
	checkFu(t, fuCase{concealed: "123456m11678s11z", winTile: "1z", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 4, Reason: FuOpenTerminalPon}, {Fu: 30, Reason: FuBase}}, 40})
}

func TestCalculateFu_WhenAnHonorPonIsCalled_ShouldScoreAnOpenTerminalPon(t *testing.T) {
	melds := []meld.Meld{newMeld(t, meld.Pon, "111z")}
	checkFu(t, fuCase{concealed: "123456m2278s", winTile: "6s", win: WinRon, rules: defaultRules(), melds: melds},
		fuResult{[]FuDetail{{Fu: 4, Reason: FuOpenTerminalPon}, {Fu: 20, Reason: FuBase}}, 30})
}

func TestCalculateFu_WhenAKanIsDeclared_ShouldScoreItByOpennessAndTerminals(t *testing.T) {
	for _, tc := range []struct {
		kind      meld.Kind
		mpsz      string
		concealed string
		want      fuResult
	}{
		{meld.ClosedKan, "2222s", "123456m11p78s", fuResult{[]FuDetail{{Fu: 16, Reason: FuClosedKan}, {Fu: 30, Reason: FuBase}}, 50}},
		{meld.OpenKan, "2222s", "123456m11p78s", fuResult{[]FuDetail{{Fu: 8, Reason: FuOpenKan}, {Fu: 20, Reason: FuBase}}, 30}},
		{meld.ClosedKan, "1111p", "123456m2278s", fuResult{[]FuDetail{{Fu: 32, Reason: FuClosedTerminalKan}, {Fu: 30, Reason: FuBase}}, 70}},
		{meld.OpenKan, "1111p", "123456m2278s", fuResult{[]FuDetail{{Fu: 16, Reason: FuOpenTerminalKan}, {Fu: 20, Reason: FuBase}}, 40}},
	} {
		t.Run(tc.kind.String()+" "+tc.mpsz, func(t *testing.T) {
			melds := []meld.Meld{newMeld(t, tc.kind, tc.mpsz)}
			checkFu(t, fuCase{concealed: tc.concealed, winTile: "6s", win: WinRon, rules: defaultRules(), melds: melds},
				tc.want)
		})
	}
}

func TestCalculateFu_WhenPinfuRonOrAClosedPonOfSimples_ShouldScore30Or40(t *testing.T) {
	checkFu(t, fuCase{concealed: "12345m123p123s11z", winTile: "6m", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 30, Reason: FuBase}}, 30})
	checkFu(t, fuCase{concealed: "33345m123p123s11z", winTile: "6m", win: WinRon, rules: defaultRules()},
		fuResult{[]FuDetail{{Fu: 4, Reason: FuClosedPon}, {Fu: 30, Reason: FuBase}}, 40})
}

func TestNextMultipleOf_ShouldRoundUpToTheMultiple(t *testing.T) {
	for _, tc := range []struct{ n, want int }{{0, 0}, {1, 10}, {10, 10}, {22, 30}, {25, 30}, {110, 110}} {
		t.Run(fmt.Sprint(tc.n), func(t *testing.T) {
			if got := nextMultipleOf(tc.n, 10); got != tc.want {
				t.Errorf("nextMultipleOf(%d, 10) = %d, want %d", tc.n, got, tc.want)
			}
		})
	}
}
