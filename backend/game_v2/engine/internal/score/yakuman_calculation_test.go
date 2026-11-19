package score_test

import (
	"errors"
	"reflect"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	yakumanTenhouShape       = "234456m66p123444s"
	yakumanKokushi           = "19m19p19s12345677z"
	yakumanKokushiSouPair    = "19m19p119s1234567z"
	yakumanSuuankouTanki     = "333m44455p111444s"
	yakumanDaisuushii        = "22s111222333444z"
	yakumanDaburuChuuren     = "11122345678999m"
	yakumanAllWinds          = "11122233344455z"
	yakumanSuuankouOrKazoe   = "111144777888999p"
	yakumanTenhouChuuren     = "11123345678999m"
	yakumanTenhouSuuankou    = "111m222p333s444s55z"
	yakumanTenhouPinfuShape  = "234678m56677899p"
	yakumanNonDealerYakuman  = 32000
	yakumanNonDealerDouble   = 64000
	yakumanDealerTsumoSingle = 16000
)

type yakumanSummary struct {
	Value   play.Value
	Yaku    []play.YakuID
	Payment play.Payment
	Total   int
	Limit   play.Option[play.Limit]
}

func yakumanSummaryOf(value score.HandValue) yakumanSummary {
	return yakumanSummary{
		Value:   value.Value,
		Yaku:    yakuIDs(value),
		Payment: value.Payment,
		Total:   value.Total,
		Limit:   value.Limit,
	}
}

func yakumanEstimate(
	tb testing.TB,
	wholeHand, winTile string,
	melds []meld.Meld,
	situation score.Situation,
	rules score.Rules,
) (yakumanSummary, error) {
	tb.Helper()
	value, err := valueOf(tb, wholeHand, winTile, melds, situation, score.Dora{}, rules)
	if err != nil {
		return yakumanSummary{}, err
	}
	return yakumanSummaryOf(value), nil
}

func yakumanExpectSummary(
	tb testing.TB,
	wholeHand, winTile string,
	melds []meld.Meld,
	situation score.Situation,
	rules score.Rules,
	want yakumanSummary,
) {
	tb.Helper()
	got, err := yakumanEstimate(tb, wholeHand, winTile, melds, situation, rules)
	if err != nil {
		tb.Errorf("EstimateHandValue(%s on %s) error = %v, want %+v", wholeHand, winTile, err, want)
		return
	}
	if !reflect.DeepEqual(got, want) {
		tb.Errorf("EstimateHandValue(%s on %s) = %+v, want %+v", wholeHand, winTile, got, want)
	}
}

func yakumanLimit(count, fu int, yaku []play.YakuID, payment play.Payment) yakumanSummary {
	return yakumanSummary{
		Value:   play.Yakuman{Count: count, Fu: play.Some(fu)},
		Yaku:    yaku,
		Payment: payment,
		Total:   payment.Sum(),
		Limit:   play.Some(play.LimitYakuman),
	}
}

func yakumanKokushiLimit(count int, yaku []play.YakuID, payment play.Payment) yakumanSummary {
	summary := yakumanLimit(count, 0, yaku, payment)
	summary.Value = play.Yakuman{Count: count}
	return summary
}

func yakumanTenhou() score.Situation {
	return score.Situation{Win: score.WinTsumo, FirstTurn: true, SeatWind: tile.East, RoundWind: tile.East}
}

func yakumanChiihou() score.Situation {
	situation := tsumo()
	situation.FirstTurn = true
	return situation
}

func yakumanNoDoubleRules() score.Rules {
	rules := defaultRules()
	rules.DoubleYakuman = false
	return rules
}

func yakumanEachKind(tb testing.TB, mpsz string) []string {
	tb.Helper()
	held := tiles(tb, mpsz)
	kinds := make([]string, 0, len(held))
	for _, t := range held {
		kinds = append(kinds, t.String())
	}
	return slices.Compact(kinds)
}

func TestEstimateHandValue_WhenFirstTurnTsumo_ShouldScoreTenhouForDealerAndChiihouForOthers(t *testing.T) {
	yakumanExpectSummary(t, yakumanTenhouShape, "4s", nil, yakumanTenhou(), defaultRules(),
		yakumanLimit(1, 30, []play.YakuID{play.YakuTenhou}, play.DealerTsumoPayment{NonDealer: 16000}))

	yakumanExpectSummary(t, yakumanTenhouShape, "4s", nil, yakumanChiihou(), defaultRules(),
		yakumanLimit(1, 30, []play.YakuID{play.YakuChiihou}, play.TsumoPayment{Dealer: 16000, NonDealer: 8000}))
}

func TestEstimateHandValue_WhenThreeDragonSets_ShouldScoreDaisangenWithTheReadingsFu(t *testing.T) {
	hand := "22m123s555666777z"
	daisangen := []play.YakuID{play.YakuDaisangen}
	payment := play.RonPayment{Discarder: yakumanNonDealerYakuman}

	yakumanExpectSummary(t, hand, "7z", nil, ron(), defaultRules(), yakumanLimit(1, 50, daisangen, payment))

	melds := []meld.Meld{chi(t, "123s"), pon(t, "555z")}
	yakumanExpectSummary(t, hand, "7z", melds, ron(), defaultRules(), yakumanLimit(1, 40, daisangen, payment))
}

func TestEstimateHandValue_WhenThreeWindSetsAndWindPair_ShouldScoreShousuushii(t *testing.T) {
	yakumanExpectSummary(t, "123s11122233344z", "4z", nil, ron(), defaultRules(),
		yakumanLimit(1, 60, []play.YakuID{play.YakuShousuushii}, play.RonPayment{Discarder: yakumanNonDealerYakuman}))
}

func TestEstimateHandValue_WhenFourWindSets_ShouldScoreDaisuushiiAsDoubleYakuman(t *testing.T) {
	yakumanExpectSummary(t, yakumanDaisuushii, "4z", nil, ron(), defaultRules(),
		yakumanLimit(2, 60, []play.YakuID{play.YakuDaisuushii}, play.RonPayment{Discarder: yakumanNonDealerDouble}))
}

func TestEstimateHandValue_WhenSevenHonorPairs_ShouldScoreTsuuiisou(t *testing.T) {
	yakumanExpectSummary(t, "11223344556677z", "7z", nil, ron(), defaultRules(),
		yakumanLimit(1, 25, []play.YakuID{play.YakuTsuuiisou}, play.RonPayment{Discarder: yakumanNonDealerYakuman}))
}

func TestEstimateHandValue_WhenTerminalSetsWonOnPairWait_ShouldScoreOnlySuuankouTanki(t *testing.T) {
	yakumanExpectSummary(t, "111999m99p111222s", "9p", nil, ron(), defaultRules(),
		yakumanLimit(2, 60, []play.YakuID{play.YakuSuuankouTanki}, play.RonPayment{Discarder: yakumanNonDealerDouble}))
}

func TestEstimateHandValue_WhenThirteenOrphans_ShouldScoreDoubleOnlyOnThirteenSidedWait(t *testing.T) {
	yakumanExpectSummary(t, yakumanKokushiSouPair, "9s", nil, ron(), defaultRules(),
		yakumanKokushiLimit(1, []play.YakuID{play.YakuKokushiMusou}, play.RonPayment{Discarder: yakumanNonDealerYakuman}))

	yakumanExpectSummary(t, yakumanKokushiSouPair, "1s", nil, ron(), defaultRules(),
		yakumanKokushiLimit(2, []play.YakuID{play.YakuDaburuKokushiMusou}, play.RonPayment{Discarder: yakumanNonDealerDouble}))
}

func TestEstimateHandValue_WhenKokushiHoldsExtraTiles_ShouldRejectTheTileCount(t *testing.T) {
	for _, row := range []struct {
		man       string
		concealed int
	}{
		{"12349", 16},
		{"122229", 17},
		{"1559", 15},
	} {
		hand := row.man + "m19p119s1234567z"

		_, err := yakumanEstimate(t, hand, "1s", nil, ron(), defaultRules())

		want := score.WrongTileCountError{Concealed: row.concealed, Melds: 0}
		if !errors.Is(err, want) {
			t.Errorf("EstimateHandValue(%s on 1s) error = %v, want %v", hand, err, want)
		}
	}
}

func TestEstimateHandValue_WhenKokushiHoldsClosedKan_ShouldRejectTheTileCount(t *testing.T) {
	melds := []meld.Meld{closedKan(t, "5555p")}

	_, err := yakumanEstimate(t, "19m155559p119s1234567z", "1s", melds, ron(), defaultRules())

	want := score.WrongTileCountError{Concealed: 13, Melds: 1}
	if !errors.Is(err, want) {
		t.Errorf("EstimateHandValue(kokushi with 5555p kan) error = %v, want %v", err, want)
	}
}

func TestEstimateHandValue_WhenAllGreenTiles_ShouldScoreRyuuiisou(t *testing.T) {
	yakumanExpectSummary(t, "22334466888s666z", "6z", nil, ron(), defaultRules(),
		yakumanLimit(1, 40, []play.YakuID{play.YakuRyuuiisou}, play.RonPayment{Discarder: yakumanNonDealerYakuman}))
}

func TestEstimateHandValue_WhenFourConcealedSets_ShouldScoreSuuankouOnlyWhenNoSetIsCompletedByRon(t *testing.T) {
	hand := "333m44555p111444s"

	yakumanExpectSummary(t, hand, "5p", nil, tsumo(), defaultRules(),
		yakumanLimit(1, 50, []play.YakuID{play.YakuSuuankou}, play.TsumoPayment{Dealer: 16000, NonDealer: 8000}))

	yakumanExpectSummary(t, hand, "5p", nil, ron(), defaultRules(), yakumanSummary{
		Value:   play.Han{Han: 4, Fu: 50},
		Yaku:    []play.YakuID{play.YakuToitoi, play.YakuSanankou},
		Payment: play.RonPayment{Discarder: 8000},
		Total:   8000,
		Limit:   play.Some(play.LimitMangan),
	})

	yakumanExpectSummary(t, yakumanSuuankouTanki, "5p", nil, tsumo(), defaultRules(),
		yakumanLimit(2, 50, []play.YakuID{play.YakuSuuankouTanki}, play.TsumoPayment{Dealer: 32000, NonDealer: 16000}))

	yakumanExpectSummary(t, "33344455577799m", "9m", nil, ron(), defaultRules(),
		yakumanLimit(2, 50, []play.YakuID{play.YakuSuuankouTanki}, play.RonPayment{Discarder: yakumanNonDealerDouble}))
}

func TestEstimateHandValue_WhenNineGatesWonOffTheNineSidedWait_ShouldScoreSingleChuurenPoutou(t *testing.T) {
	yakumanExpectSummary(t, "11123456789999m", "1m", nil, ron(), defaultRules(),
		yakumanLimit(1, 40, []play.YakuID{play.YakuChuurenPoutou}, play.RonPayment{Discarder: yakumanNonDealerYakuman}))
}

func TestEstimateHandValue_WhenNineGatesWonOnTheNineSidedWait_ShouldScoreDaburuChuurenPoutou(t *testing.T) {
	for _, row := range []struct {
		hand    string
		winTile string
		fu      int
	}{
		{yakumanDaburuChuuren, "2m", 50},
		{"11123456789999m", "9m", 40},
		{"11112345678999m", "1m", 40},
	} {
		yakumanExpectSummary(t, row.hand, row.winTile, nil, ron(), defaultRules(),
			yakumanLimit(2, row.fu, []play.YakuID{play.YakuDaburuChuurenPoutou},
				play.RonPayment{Discarder: yakumanNonDealerDouble}))
	}
}

func TestEstimateHandValue_WhenNineGatesShapeMixesSuitsOrHonors_ShouldScoreWithoutChuurenPoutou(t *testing.T) {
	for _, row := range []struct {
		hand    string
		winTile string
		want    yakumanSummary
	}{
		{"12345678999p111z", "4p", yakumanSummary{
			Value:   play.Han{Han: 6, Fu: 40},
			Yaku:    []play.YakuID{play.YakuRoundWindEast, play.YakuIttsu, play.YakuHonitsu},
			Payment: play.RonPayment{Discarder: 12000},
			Total:   12000,
			Limit:   play.Some(play.LimitHaneman),
		}},
		{"999m11123456789s", "4s", yakumanSummary{
			Value:   play.Han{Han: 2, Fu: 40},
			Yaku:    []play.YakuID{play.YakuIttsu},
			Payment: play.RonPayment{Discarder: 2600},
			Total:   2600,
		}},
	} {
		yakumanExpectSummary(t, row.hand, row.winTile, nil, ron(), defaultRules(), row.want)
	}
}

func TestEstimateHandValue_WhenNineGatesShapeHoldsClosedKan_ShouldScoreChinitsuWithoutChuurenPoutou(t *testing.T) {
	melds := []meld.Meld{closedKan(t, "9999p")}

	yakumanExpectSummary(t, "111234566789999p", "3p", melds, ron(), defaultRules(), yakumanSummary{
		Value:   play.Han{Han: 6, Fu: 70},
		Yaku:    []play.YakuID{play.YakuChinitsu},
		Payment: play.RonPayment{Discarder: 12000},
		Total:   12000,
		Limit:   play.Some(play.LimitHaneman),
	})
}

func TestEstimateHandValue_WhenFourKans_ShouldScoreSuukantsu(t *testing.T) {
	melds := []meld.Meld{
		openKan(t, "1111s"),
		openKan(t, "3333s"),
		openKan(t, "5555p"),
		openKan(t, "2222m"),
	}

	yakumanExpectSummary(t, "2222m445555p11113333s", "4p", melds, ron(), defaultRules(),
		yakumanLimit(1, 70, []play.YakuID{play.YakuSuukantsu}, play.RonPayment{Discarder: yakumanNonDealerYakuman}))
}

func TestEstimateHandValue_WhenDoubleYakumanDisabled_ShouldScoreDoubleFormsAsOneYakuman(t *testing.T) {
	rules := yakumanNoDoubleRules()
	single := play.RonPayment{Discarder: yakumanNonDealerYakuman}

	yakumanExpectSummary(t, yakumanKokushiSouPair, "1s", nil, ron(), rules,
		yakumanKokushiLimit(1, []play.YakuID{play.YakuDaburuKokushiMusou}, single))

	yakumanExpectSummary(t, yakumanSuuankouTanki, "5p", nil, tsumo(), rules,
		yakumanLimit(1, 50, []play.YakuID{play.YakuSuuankouTanki}, play.TsumoPayment{Dealer: 16000, NonDealer: 8000}))

	yakumanExpectSummary(t, yakumanDaburuChuuren, "2m", nil, ron(), rules,
		yakumanLimit(1, 50, []play.YakuID{play.YakuDaburuChuurenPoutou}, single))

	yakumanExpectSummary(t, yakumanDaisuushii, "4z", nil, ron(), rules,
		yakumanLimit(1, 60, []play.YakuID{play.YakuDaisuushii}, single))
}

func TestEstimateHandValue_WhenEveryHonorYakumanStacks_ShouldScoreSextupleYakuman(t *testing.T) {
	yakumanExpectSummary(t, yakumanAllWinds, "5z", nil, yakumanTenhou(), defaultRules(), yakumanLimit(6, 60,
		[]play.YakuID{play.YakuTsuuiisou, play.YakuDaisuushii, play.YakuSuuankouTanki, play.YakuTenhou},
		play.DealerTsumoPayment{NonDealer: 96000}))

	melds := []meld.Meld{
		closedKan(t, "1111z"),
		closedKan(t, "2222z"),
		closedKan(t, "3333z"),
		closedKan(t, "4444z"),
	}
	yakumanExpectSummary(t, "111122223333444455z", "5z", melds, ron(), defaultRules(), yakumanLimit(6, 170,
		[]play.YakuID{play.YakuSuukantsu, play.YakuTsuuiisou, play.YakuDaisuushii, play.YakuSuuankouTanki},
		play.RonPayment{Discarder: 192000}))
}

func TestEstimateHandValue_WhenKokushiStacksWithFirstTurnYakuman_ShouldCountEveryYakuman(t *testing.T) {
	kokushi := play.YakuKokushiMusou
	daburu := play.YakuDaburuKokushiMusou
	for _, row := range []struct {
		winTile   string
		situation score.Situation
		count     int
		yaku      []play.YakuID
		payment   play.Payment
	}{
		{"1z", tsumo(), 1, []play.YakuID{kokushi}, play.TsumoPayment{Dealer: 16000, NonDealer: 8000}},
		{"1z", yakumanTenhou(), 3, []play.YakuID{daburu, play.YakuTenhou}, play.DealerTsumoPayment{NonDealer: 48000}},
		{
			"1z", yakumanChiihou(), 2,
			[]play.YakuID{kokushi, play.YakuChiihou},
			play.TsumoPayment{Dealer: 32000, NonDealer: 16000},
		},
		{"7z", tsumo(), 2, []play.YakuID{daburu}, play.TsumoPayment{Dealer: 32000, NonDealer: 16000}},
		{"7z", yakumanTenhou(), 3, []play.YakuID{daburu, play.YakuTenhou}, play.DealerTsumoPayment{NonDealer: 48000}},
		{
			"7z", yakumanChiihou(), 3,
			[]play.YakuID{daburu, play.YakuChiihou},
			play.TsumoPayment{Dealer: 48000, NonDealer: 24000},
		},
	} {
		yakumanExpectSummary(t, yakumanKokushi, row.winTile, nil, row.situation, defaultRules(),
			yakumanKokushiLimit(row.count, row.yaku, row.payment))
	}
}

func TestEstimateHandValue_WhenTenhouOnAnyWinTile_ShouldNameTheDoubleForm(t *testing.T) {
	for _, rulesRow := range []struct {
		name  string
		rules score.Rules
		count int
	}{
		{"double yakuman", defaultRules(), 3},
		{"single yakuman", yakumanNoDoubleRules(), 2},
	} {
		for _, handRow := range []struct {
			mpsz       string
			doubleForm play.YakuID
		}{
			{yakumanTenhouChuuren, play.YakuDaburuChuurenPoutou},
			{yakumanKokushi, play.YakuDaburuKokushiMusou},
			{yakumanTenhouSuuankou, play.YakuSuuankouTanki},
		} {
			for _, winTile := range yakumanEachKind(t, handRow.mpsz) {
				got, err := yakumanEstimate(t, handRow.mpsz, winTile, nil, yakumanTenhou(), rulesRow.rules)
				if err != nil {
					t.Fatalf("EstimateHandValue(%s on %s, %s) error = %v", handRow.mpsz, winTile, rulesRow.name, err)
				}

				yakuman, isYakuman := got.Value.(play.Yakuman)
				wantYaku := []play.YakuID{handRow.doubleForm, play.YakuTenhou}
				wantPayment := play.DealerTsumoPayment{NonDealer: yakumanDealerTsumoSingle * rulesRow.count}
				if !isYakuman || yakuman.Count != rulesRow.count || !slices.Equal(got.Yaku, wantYaku) ||
					got.Payment != wantPayment {
					t.Errorf("EstimateHandValue(%s on %s, %s) = %v %v %v, want %d yakuman %v %v",
						handRow.mpsz, winTile, rulesRow.name, got.Value, got.Yaku, got.Payment,
						rulesRow.count, wantYaku, wantPayment)
				}
			}
		}
	}
}

func TestEstimateHandValue_WhenTenhouOnAnyWinTile_ShouldPayTheSame(t *testing.T) {
	paid := func(tb testing.TB, mpsz, winTile string, rules score.Rules) (yakumanSummary, error) {
		tb.Helper()
		summary, err := yakumanEstimate(tb, mpsz, winTile, nil, yakumanTenhou(), rules)
		if err != nil {
			return yakumanSummary{}, err
		}
		yakuman, isYakuman := summary.Value.(play.Yakuman)
		if !isYakuman {
			tb.Fatalf("EstimateHandValue(%s on %s) = %v, want a yakuman", mpsz, winTile, summary.Value)
		}
		summary.Value = play.Yakuman{Count: yakuman.Count}
		return summary, nil
	}
	for _, rulesRow := range []struct {
		name  string
		rules score.Rules
	}{
		{"double yakuman", defaultRules()},
		{"single yakuman", yakumanNoDoubleRules()},
	} {
		for _, mpsz := range []string{
			yakumanTenhouChuuren, yakumanKokushi, yakumanTenhouSuuankou, yakumanTenhouPinfuShape,
		} {
			kinds := yakumanEachKind(t, mpsz)
			first, firstErr := paid(t, mpsz, kinds[0], rulesRow.rules)
			for _, winTile := range kinds {
				got, err := paid(t, mpsz, winTile, rulesRow.rules)

				if !errors.Is(err, firstErr) || !reflect.DeepEqual(got, first) {
					t.Errorf("EstimateHandValue(%s on %s, %s) = %+v, %v, want %+v, %v",
						mpsz, winTile, rulesRow.name, got, err, first, firstErr)
				}
			}
		}
	}
}

func TestEstimateHandValue_WhenTenhou_ShouldKeepTheFuOfTheGivenWinTile(t *testing.T) {
	for _, row := range []struct {
		winTile string
		fu      int
	}{
		{"6m", 20},
		{"9p", 30},
	} {
		got, err := yakumanEstimate(t, yakumanTenhouPinfuShape, row.winTile, nil, yakumanTenhou(), score.HandRules())

		want := play.Yakuman{Count: 1, Fu: play.Some(row.fu)}
		if err != nil || got.Value != want {
			t.Errorf("EstimateHandValue(%s on %s) = %v, %v, want %v",
				yakumanTenhouPinfuShape, row.winTile, got.Value, err, want)
		}
	}
}

func TestEstimateHandValue_WhenChiihou_ShouldKeepTheWaitOfItsDrawnTile(t *testing.T) {
	got, err := yakumanEstimate(t, yakumanTenhouChuuren, "1m", nil, yakumanChiihou(), defaultRules())

	want := []play.YakuID{play.YakuChuurenPoutou, play.YakuChiihou}
	if err != nil || !slices.Equal(got.Yaku, want) {
		t.Errorf("EstimateHandValue(%s on 1m) = %v, %v, want %v", yakumanTenhouChuuren, got.Yaku, err, want)
	}
}

func TestEstimateHandValue_WhenSevenPairsOfTwoToEight_ShouldScoreRyanpeikouChinitsu(t *testing.T) {
	for _, row := range []struct {
		mpsz    string
		winTile string
	}{
		{"22334455667788p", "8p"},
		{"22334455667788s", "8s"},
		{"22334455667788m", "8m"},
	} {
		yakumanExpectSummary(t, row.mpsz, row.winTile, nil, ron(), defaultRules(), yakumanSummary{
			Value:   play.Han{Han: 11, Fu: 30},
			Yaku:    []play.YakuID{play.YakuPinfu, play.YakuTanyao, play.YakuRyanpeikou, play.YakuChinitsu},
			Payment: play.RonPayment{Discarder: 24000},
			Total:   24000,
			Limit:   play.Some(play.LimitSanbaiman),
		})
	}
}

func TestEstimateHandValue_WhenSuuankouCostsTheSameAsKazoe_ShouldScoreSuuankou(t *testing.T) {
	melds := []meld.Meld{closedKan(t, "1111p")}
	dora := score.Dora{Indicators: tiles(t, "6p7p")}

	value, err := valueOf(t, yakumanSuuankouOrKazoe, "8p", melds, tsumo(), dora, defaultRules())
	if err != nil {
		t.Fatalf("EstimateHandValue(%s on 8p) error = %v", yakumanSuuankouOrKazoe, err)
	}

	want := yakumanLimit(1, 70, []play.YakuID{play.YakuSuuankou}, play.TsumoPayment{Dealer: 16000, NonDealer: 8000})
	if got := yakumanSummaryOf(value); !reflect.DeepEqual(got, want) {
		t.Errorf("EstimateHandValue(%s on 8p) = %+v, want %+v", yakumanSuuankouOrKazoe, got, want)
	}
	names := make([]string, 0, len(value.Yaku))
	for _, y := range value.Yaku {
		names = append(names, y.ID.Name())
	}
	if want := []string{"Suu Ankou"}; !slices.Equal(names, want) {
		t.Errorf("EstimateHandValue(%s on 8p) yaku names = %v, want %v", yakumanSuuankouOrKazoe, names, want)
	}
}
