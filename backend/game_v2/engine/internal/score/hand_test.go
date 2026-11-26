package score_test

import (
	"errors"
	"fmt"
	"reflect"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	handPlain       = "123444s234456m66p"
	handPlainKan    = "1234444s234456m66p"
	handTanyaoPinfu = "234567p23455678s"
	handKokushi     = "19m19p119s1234567z"
	handNotWinning  = "123344s234456m66p"
)

func handEstimate(
	tb testing.TB,
	wholeHand, winTile string,
	melds []meld.Meld,
	situation score.Situation,
) (score.HandValue, error) {
	tb.Helper()
	return valueOf(tb, wholeHand, winTile, melds, situation, score.Dora{}, defaultRules())
}

func handValue(
	tb testing.TB,
	wholeHand, winTile string,
	melds []meld.Meld,
	situation score.Situation,
) score.HandValue {
	tb.Helper()
	value, err := handEstimate(tb, wholeHand, winTile, melds, situation)
	if err != nil {
		tb.Fatalf("EstimateHandValue(%s, %s, %+v) error = %v", wholeHand, winTile, situation, err)
	}

	return value
}

func handEstimateConcealed(
	tb testing.TB,
	concealed, winTile string,
	melds []meld.Meld,
	situation score.Situation,
) (score.HandValue, error) {
	tb.Helper()
	h := score.Hand{Concealed: tiles(tb, concealed), WinTile: oneTile(tb, winTile), Melds: melds}
	return score.EstimateHandValue(h, situation, score.Dora{}, defaultRules())
}

func handEstimatePlain(tb testing.TB, situation score.Situation) (score.HandValue, error) {
	tb.Helper()
	return handEstimate(tb, handPlain, "4s", nil, situation)
}

func handEstimatePlainKan(tb testing.TB, situation score.Situation) (score.HandValue, error) {
	tb.Helper()
	return handEstimate(tb, handPlainKan, "1s", []meld.Meld{closedKan(tb, "4444s")}, situation)
}

func handWonBy(win score.Win) score.Situation {
	return score.Situation{Win: win, SeatWind: tile.South, RoundWind: tile.East}
}

func handDealerWonBy(win score.Win) score.Situation {
	return score.Situation{Win: win, SeatWind: tile.East, RoundWind: tile.East}
}

func handOnFirstTurn(situation score.Situation) score.Situation {
	situation.FirstTurn = true
	return situation
}

func handWithIppatsu(situation score.Situation) score.Situation {
	situation.Riichi = play.Some(play.Riichi{Ippatsu: true})
	return situation
}

func handWantErr(tb testing.TB, call string, got, want error) {
	tb.Helper()
	if !errors.Is(got, want) {
		tb.Errorf("%s error = %v, want %v", call, got, want)
	}
}

func handWantValue(tb testing.TB, call string, got, want score.HandValue) {
	tb.Helper()
	if !reflect.DeepEqual(got, want) {
		tb.Errorf("%s =\n%+v\nwant\n%+v", call, got, want)
	}
}

func TestEstimateHandValue_WhenRiichiWithOpenMeld_ShouldReturnOpenHandRiichiError(t *testing.T) {
	melds := []meld.Meld{chi(t, "123s")}

	_, err := handEstimate(t, handPlain, "4s", melds, withRiichi(ron()))
	handWantErr(t, "EstimateHandValue(open riichi)", err, score.OpenHandRiichiError{})
}

func TestEstimateHandValue_WhenDoubleRiichiWithOpenMeld_ShouldReturnOpenHandRiichiError(t *testing.T) {
	melds := []meld.Meld{chi(t, "123s")}
	situation := ron()
	situation.Riichi = play.Some(play.Riichi{Double: true})

	_, err := handEstimate(t, handPlain, "4s", melds, situation)
	handWantErr(t, "EstimateHandValue(open double riichi)", err, score.OpenHandRiichiError{})
}

func TestEstimateHandValue_WhenTilesDoNotWin_ShouldReturnNotWinningError(t *testing.T) {
	_, err := handEstimate(t, handNotWinning, "4s", nil, ron())
	handWantErr(t, "EstimateHandValue("+handNotWinning+")", err, score.NotWinningError{})
}

func TestEstimateHandValue_WhenExtraHonorsAdded_ShouldReturnWrongTileCountError(t *testing.T) {
	for _, tc := range []struct {
		honors    string
		concealed int
	}{
		{"1z", 14},
		{"1111z", 17},
	} {
		t.Run(tc.honors, func(t *testing.T) {
			wholeHand := "234567m23455p678s" + tc.honors

			_, err := handEstimate(t, wholeHand, "8s", nil, ron())
			handWantErr(t, "EstimateHandValue("+wholeHand+")", err, score.WrongTileCountError{Concealed: tc.concealed})
		})
	}
}

func TestEstimateHandValue_WhenHonorsCannotBeDivided_ShouldReturnNotWinningError(t *testing.T) {
	for _, wholeHand := range []string{"234567m2355p678s1z", "234567m5p678s1111z"} {
		t.Run(wholeHand, func(t *testing.T) {
			_, err := handEstimate(t, wholeHand, "8s", nil, ron())
			handWantErr(t, "EstimateHandValue("+wholeHand+")", err, score.NotWinningError{})
		})
	}
}

func TestEstimateHandValue_WhenOpenHandHasNoYaku_ShouldReturnNoYakuError(t *testing.T) {
	_, err := handEstimate(t, handPlain, "4s", []meld.Meld{chi(t, "123s")}, ron())
	handWantErr(t, "EstimateHandValue(open hand without yaku)", err, score.NoYakuError{})
}

func TestEstimateHandValue_WhenHandHasOnlyDora_ShouldReturnNoYakuError(t *testing.T) {
	dora := score.Dora{Indicators: tiles(t, "1m")}

	_, err := valueOf(t, "123m234p340678s22z", "2m", nil, ron(), dora, defaultRules())
	handWantErr(t, "EstimateHandValue(dora without yaku)", err, score.NoYakuError{})
}

func TestEstimateHandValue_WhenRinshanWithoutKan_ShouldReturnRinshanWithoutKanError(t *testing.T) {
	situation := handWonBy(score.WinRinshan)

	_, closedErr := handEstimatePlain(t, situation)
	_, ponErr := handEstimate(t, handPlain, "1s", []meld.Meld{pon(t, "444s")}, situation)
	handWantErr(t, "EstimateHandValue(closed rinshan)", closedErr, score.RinshanWithoutKanError{})
	handWantErr(t, "EstimateHandValue(rinshan with pon)", ponErr, score.RinshanWithoutKanError{})
}

func TestEstimateHandValue_WhenIppatsuOnRinshan_ShouldReturnIppatsuWithRinshanError(t *testing.T) {
	_, err := handEstimatePlainKan(t, handWithIppatsu(handWonBy(score.WinRinshan)))
	handWantErr(t, "EstimateHandValue(ippatsu rinshan)", err, score.IppatsuWithRinshanError{})
}

func TestEstimateHandValue_WhenDealerWinsOnFirstTurnAfterKan_ShouldReturnFirstTurnWithMeldError(t *testing.T) {
	_, err := handEstimatePlainKan(t, handOnFirstTurn(handDealerWonBy(score.WinRinshan)))
	handWantErr(t, "EstimateHandValue(dealer first-turn rinshan)", err, score.FirstTurnWithMeldError{})
}

func TestEstimateHandValue_WhenFirstTurnTsumo_ShouldScoreChiihouForNonDealerAndTenhouForDealer(t *testing.T) {
	for _, tc := range []struct {
		name      string
		situation score.Situation
		yaku      play.YakuID
		payment   play.Payment
		total     int
	}{
		{"chiihou", handOnFirstTurn(tsumo()), play.YakuChiihou, play.TsumoPayment{Dealer: 16000, NonDealer: 8000}, 32000},
		{
			"tenhou",
			handOnFirstTurn(handDealerWonBy(score.WinTsumo)),
			play.YakuTenhou,
			play.DealerTsumoPayment{NonDealer: 16000},
			48000,
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got, err := handEstimatePlain(t, tc.situation)
			if err != nil {
				t.Fatalf("EstimateHandValue(%s) error = %v", tc.name, err)
			}

			if ids := yakuIDs(got); !reflect.DeepEqual(ids, []play.YakuID{tc.yaku}) {
				t.Errorf("EstimateHandValue(%s).Yaku = %v, want [%v]", tc.name, ids, tc.yaku)
			}
			if want := (play.Yakuman{Count: 1, Fu: play.Some(30)}); got.Value != want {
				t.Errorf("EstimateHandValue(%s).Value = %+v, want %+v", tc.name, got.Value, want)
			}
			if want := play.Some(play.LimitYakuman); got.Limit != want {
				t.Errorf("EstimateHandValue(%s).Limit = %+v, want %+v", tc.name, got.Limit, want)
			}
			if got.Payment != tc.payment || got.Total != tc.total {
				t.Errorf("EstimateHandValue(%s) payment, total = %+v, %d, want %+v, %d",
					tc.name, got.Payment, got.Total, tc.payment, tc.total)
			}
		})
	}
}

func TestEstimateHandValue_WhenNonDealerWinsOnFirstTurnAfterKan_ShouldReturnFirstTurnWithMeldError(t *testing.T) {
	_, err := handEstimatePlainKan(t, handOnFirstTurn(handWonBy(score.WinRinshan)))
	handWantErr(t, "EstimateHandValue(first-turn rinshan)", err, score.FirstTurnWithMeldError{})
}

func TestEstimateHandValue_WhenFirstTurnRonWithClosedKan_ShouldReturnFirstTurnWithMeldError(t *testing.T) {
	_, err := handEstimatePlainKan(t, handOnFirstTurn(ron()))
	handWantErr(t, "EstimateHandValue(first-turn ron with kan)", err, score.FirstTurnWithMeldError{})
}

func TestEstimateHandValue_WhenFirstTurnWinAfterAnyCall_ShouldReturnFirstTurnWithMeldError(t *testing.T) {
	for _, tc := range []struct {
		name      string
		wholeHand string
		winTile   string
		meld      meld.Meld
		situation score.Situation
	}{
		{"chi", handPlain, "4s", chi(t, "123s"), handOnFirstTurn(ron())},
		{"pon", handPlain, "1s", pon(t, "444s"), handOnFirstTurn(ron())},
		{"open kan", handPlainKan, "1s", openKan(t, "4444s"), handOnFirstTurn(tsumo())},
	} {
		t.Run(tc.name, func(t *testing.T) {
			_, err := handEstimate(t, tc.wholeHand, tc.winTile, []meld.Meld{tc.meld}, tc.situation)
			handWantErr(t, "EstimateHandValue(first turn after "+tc.name+")", err, score.FirstTurnWithMeldError{})
		})
	}
}

func TestEstimateHandValue_WhenFirstTurnWinWithRiichi_ShouldReturnFirstTurnWithRiichiError(t *testing.T) {
	for _, riichi := range []play.Riichi{{}, {Double: true, Ippatsu: true}} {
		t.Run(fmt.Sprintf("%+v", riichi), func(t *testing.T) {
			for _, win := range []score.Win{score.WinRon, score.WinTsumo} {
				situation := handOnFirstTurn(handWonBy(win))
				situation.Riichi = play.Some(riichi)

				_, err := handEstimatePlain(t, situation)
				if !errors.Is(err, score.FirstTurnWithRiichiError{}) {
					t.Errorf("EstimateHandValue(%+v, win %d) error = %v, want %v",
						riichi, win, err, score.FirstTurnWithRiichiError{})
				}
			}
		})
	}
}

func TestEstimateHandValue_WhenDealerRonsOnFirstTurn_ShouldReturnFirstTurnDealerRonError(t *testing.T) {
	_, err := handEstimatePlain(t, handOnFirstTurn(handDealerWonBy(score.WinRon)))
	handWantErr(t, "EstimateHandValue(dealer first-turn ron)", err, score.FirstTurnDealerRonError{})
}

func TestEstimateHandValue_WhenFirstTurnWinIsChankanHouteiOrHaitei_ShouldReturnFirstTurnSpecialWinError(t *testing.T) {
	for _, win := range []score.Win{score.WinChankan, score.WinHoutei, score.WinHaitei} {
		t.Run(fmt.Sprint(win), func(t *testing.T) {
			for _, situation := range []score.Situation{handWonBy(win), handDealerWonBy(win)} {
				_, err := handEstimatePlain(t, handOnFirstTurn(situation))
				if !errors.Is(err, score.FirstTurnSpecialWinError{}) {
					t.Errorf("EstimateHandValue(first turn %+v) error = %v, want %v",
						situation, err, score.FirstTurnSpecialWinError{})
				}
			}
		})
	}
}

func TestEstimateHandValue_WhenWinningTileCountedInMeld_ShouldReturnWrongTileCountError(t *testing.T) {
	for _, m := range []meld.Meld{pon(t, "111m"), closedKan(t, "1111m")} {
		t.Run(m.String(), func(t *testing.T) {
			_, err := handEstimateConcealed(t, "234m456p789s11z", "1m", []meld.Meld{m}, ron())
			if want := (score.WrongTileCountError{Concealed: 11, Melds: 1}); !errors.Is(err, want) {
				t.Errorf("EstimateHandValue(winning tile in %v) error = %v, want %v", m.Tiles(), err, want)
			}
		})
	}
}

func TestEstimateHandValue_WhenWinningTileMatchesPonKind_ShouldScoreHand(t *testing.T) {
	melds := []meld.Meld{pon(t, "111m")}

	got := handValue(t, "111123m456p789s55z", "1m", melds, handWonBy(score.WinHoutei))
	if want := (play.Han{Han: 1, Fu: 30}); got.Value != want {
		t.Errorf("EstimateHandValue(fourth 1m beside a 1m pon).Value = %+v, want %+v", got.Value, want)
	}
}

func TestEstimateHandValue_WhenSetsAndMeldsAreNotFourAndPair_ShouldReturnWrongTileCountError(t *testing.T) {
	fourPons := []meld.Meld{pon(t, "666s"), pon(t, "777s"), pon(t, "888s"), pon(t, "111z")}

	_, tooManySets := handEstimate(t, "123456789m11122p666s777s888s111z", "1m", fourPons, ron())
	_, tooFewSets := handEstimate(t, "11z666s777s888s", "1z", fourPons[:3], ron())
	handWantErr(t, "EstimateHandValue(too many sets)", tooManySets, score.WrongTileCountError{Concealed: 13, Melds: 4})
	handWantErr(t, "EstimateHandValue(too few sets)", tooFewSets, score.WrongTileCountError{Concealed: 1, Melds: 3})
}

func TestEstimateHandValue_WhenFiveTilesOfOneKind_ShouldReturnTooManyCopiesError(t *testing.T) {
	for _, tc := range []struct {
		name      string
		concealed string
		winTile   string
		melds     []meld.Meld
		kind      tile.Kind
	}{
		{"in hand", "1111m234567p999s", "1m", nil, 0},
		{"with pon", "11m234567p99s", "9s", []meld.Meld{pon(t, "111m")}, 0},
		{"winning tile and kan", "234567p99s55z", "1m", []meld.Meld{closedKan(t, "1111m")}, 0},
		{"red five", "0555p234567m999s", "5p", nil, 13},
	} {
		t.Run(tc.name, func(t *testing.T) {
			_, err := handEstimateConcealed(t, tc.concealed, tc.winTile, tc.melds, ron())
			handWantErr(t, "EstimateHandValue("+tc.name+")", err, tile.TooManyCopiesError{Kind: tc.kind})
		})
	}
}

func TestEstimateHandValue_WhenWrongCountAndTooManyCopies_ShouldReturnWrongTileCountError(t *testing.T) {
	_, err := handEstimateConcealed(t, "11111m", "1m", nil, ron())
	handWantErr(t, "EstimateHandValue(11111m, 1m)", err, score.WrongTileCountError{Concealed: 5})
}

func TestEstimateHandValue_WhenTooManyCopiesAndInvalidSituation_ShouldReturnTooManyCopiesError(t *testing.T) {
	situation := withRiichi(handWonBy(score.WinRinshan))

	_, err := handEstimateConcealed(t, "11m234567p99s", "9s", []meld.Meld{pon(t, "111m")}, situation)
	handWantErr(t, "EstimateHandValue(five 1m, open riichi rinshan)", err, tile.TooManyCopiesError{Kind: 0})
}

func TestEstimateHandValue_WhenSeveralSituationChecksFail_ShouldReturnFirstInOrder(t *testing.T) {
	ippatsuRinshan := handWithIppatsu(handWonBy(score.WinRinshan))

	_, openRiichiOnRinshan := handEstimate(t, handPlain, "4s", []meld.Meld{chi(t, "123s")}, ippatsuRinshan)
	_, ippatsuRinshanWithoutKan := handEstimatePlain(t, ippatsuRinshan)
	_, firstTurnIppatsuRinshan := handEstimatePlainKan(t, handOnFirstTurn(ippatsuRinshan))
	_, firstTurnRiichiWithKan := handEstimatePlainKan(t, handOnFirstTurn(withRiichi(handWonBy(score.WinRinshan))))
	_, firstTurnRiichiHaitei := handEstimatePlain(t, handOnFirstTurn(withRiichi(handWonBy(score.WinHaitei))))
	_, firstTurnDealerRiichiRon := handEstimatePlain(t, handOnFirstTurn(withRiichi(handDealerWonBy(score.WinRon))))
	handWantErr(t, "EstimateHandValue(open riichi on rinshan)", openRiichiOnRinshan, score.OpenHandRiichiError{})
	handWantErr(t, "EstimateHandValue(ippatsu rinshan without kan)", ippatsuRinshanWithoutKan,
		score.RinshanWithoutKanError{})
	handWantErr(t, "EstimateHandValue(first-turn ippatsu rinshan)", firstTurnIppatsuRinshan,
		score.IppatsuWithRinshanError{})
	handWantErr(t, "EstimateHandValue(first-turn riichi with kan)", firstTurnRiichiWithKan,
		score.FirstTurnWithMeldError{})
	handWantErr(t, "EstimateHandValue(first-turn riichi haitei)", firstTurnRiichiHaitei,
		score.FirstTurnSpecialWinError{})
	handWantErr(t, "EstimateHandValue(first-turn dealer riichi ron)", firstTurnDealerRiichiRon,
		score.FirstTurnWithRiichiError{})
}

func TestEstimateHandValue_WhenInvalidSituationAndNotWinning_ShouldReturnSituationError(t *testing.T) {
	_, err := handEstimate(t, handNotWinning, "4s", nil, handWonBy(score.WinRinshan))
	handWantErr(t, "EstimateHandValue(non-winning rinshan without kan)", err, score.RinshanWithoutKanError{})
}

func TestEstimateHandValue_WhenOpenHandDoesNotWin_ShouldReturnNotWinningError(t *testing.T) {
	_, err := handEstimate(t, handNotWinning, "4s", []meld.Meld{chi(t, "123s")}, ron())
	handWantErr(t, "EstimateHandValue(open non-winning hand)", err, score.NotWinningError{})
}

func TestEstimateHandValue_WhenNoHonbaOrSticks_ShouldTotalThePaymentAlone(t *testing.T) {
	situation := ron()
	situation.Honba = 0
	situation.RiichiSticks = 0

	got := handValue(t, handTanyaoPinfu, "8s", nil, situation)
	if got.Total != 2000 {
		t.Errorf("EstimateHandValue(tanyao pinfu ron).Total = %d, want 2000", got.Total)
	}
}

func TestEstimateHandValue_WhenHonba_ShouldAddHonbaToEveryPayment(t *testing.T) {
	for _, tc := range []struct {
		situation score.Situation
		payment   play.Payment
		total     int
	}{
		{ron(), play.RonPayment{Discarder: 2600}, 2600},
		{handDealerWonBy(score.WinRon), play.RonPayment{Discarder: 3500}, 3500},
		{tsumo(), play.TsumoPayment{Dealer: 1500, NonDealer: 900}, 3300},
		{handDealerWonBy(score.WinTsumo), play.DealerTsumoPayment{NonDealer: 1500}, 4500},
	} {
		t.Run(fmt.Sprint(tc.total), func(t *testing.T) {
			situation := tc.situation
			situation.Honba = 2

			got := handValue(t, handTanyaoPinfu, "8s", nil, situation)
			if got.Payment != tc.payment || got.Total != tc.total {
				t.Errorf("EstimateHandValue(%+v) payment, total = %+v, %d, want %+v, %d",
					situation, got.Payment, got.Total, tc.payment, tc.total)
			}
		})
	}
}

func TestEstimateHandValue_WhenRiichiSticks_ShouldAddThemToTheTotalOnly(t *testing.T) {
	situation := withRiichi(ron())
	situation.RiichiSticks = 2

	got := handValue(t, handTanyaoPinfu, "8s", nil, situation)
	if want := (play.Han{Han: 3, Fu: 30}); got.Value != want {
		t.Errorf("EstimateHandValue(2 riichi sticks).Value = %+v, want %+v", got.Value, want)
	}
	if want := (play.RonPayment{Discarder: 3900}); got.Payment != want {
		t.Errorf("EstimateHandValue(2 riichi sticks).Payment = %+v, want %+v", got.Payment, want)
	}
	if got.Total != 5900 {
		t.Errorf("EstimateHandValue(2 riichi sticks).Total = %d, want 5900", got.Total)
	}
}

func TestHandValueString_WhenHanHand_ShouldShowHanAndFu(t *testing.T) {
	plain, err := handEstimatePlain(t, withRiichi(ron()))
	if err != nil {
		t.Fatalf("EstimateHandValue(riichi ron) error = %v", err)
	}

	tanyaoPinfu := handValue(t, handTanyaoPinfu, "8s", nil, withRiichi(ron()))
	if got := plain.Value.String(); got != "1 han, 40 fu" {
		t.Errorf("EstimateHandValue(riichi ron).Value.String() = %q, want %q", got, "1 han, 40 fu")
	}
	if got := tanyaoPinfu.Value.String(); got != "3 han, 30 fu" {
		t.Errorf("EstimateHandValue(riichi tanyao pinfu).Value.String() = %q, want %q", got, "3 han, 30 fu")
	}
}

func TestHandValueString_WhenYakumanHand_ShouldShowYakumanCount(t *testing.T) {
	single := handValue(t, handKokushi, "7z", nil, tsumo())
	double := handValue(t, handKokushi, "1s", nil, ron())
	if got := single.Value.String(); got != "yakuman" {
		t.Errorf("EstimateHandValue(kokushi on 7z).Value.String() = %q, want %q", got, "yakuman")
	}
	if got := double.Value.String(); got != "2x yakuman" {
		t.Errorf("EstimateHandValue(kokushi on 1s).Value.String() = %q, want %q", got, "2x yakuman")
	}
}

func TestEstimateHandValue_WhenTsumoReadsAsPinfuOrTerminalPon_ShouldPickTerminalPonAt30Fu(t *testing.T) {
	got := handValue(t, "234m11123456777s", "4s", nil, tsumo())
	if han, ok := got.Value.(play.Han); !ok || han.Fu != 30 {
		t.Errorf("EstimateHandValue(234m11123456777s, 4s).Value = %+v, want 30 fu", got.Value)
	}

	want := []score.FuDetail{{Fu: 20, Reason: score.FuBase}, {Fu: 8, Reason: score.FuClosedTerminalPon}, {Fu: 2, Reason: score.FuTsumo}}
	if !reflect.DeepEqual(got.FuDetails, want) {
		t.Errorf("EstimateHandValue(234m11123456777s, 4s).FuDetails = %+v, want %+v", got.FuDetails, want)
	}
}

func TestEstimateHandValue_WhenFuDetailsTie_ShouldOrderWaitPairThenSetsByKind(t *testing.T) {
	melds := []meld.Meld{pon(t, "111z"), pon(t, "222p")}

	got, err := handEstimateConcealed(t, "333m46m55z", "5m", melds, ron())
	if err != nil {
		t.Fatalf("EstimateHandValue(333m46m55z, 5m) error = %v", err)
	}

	handWantValue(t, "EstimateHandValue(333m46m55z, 5m)", got, score.HandValue{
		Value:   play.Han{Han: 1, Fu: 40},
		Payment: play.RonPayment{Discarder: 1300},
		Total:   1300,
		Yaku:    []score.Yaku{{ID: play.YakuRoundWindEast, Han: 1}},
		FuDetails: []score.FuDetail{
			{Fu: 20, Reason: score.FuBase},
			{Fu: 4, Reason: score.FuClosedPon},
			{Fu: 4, Reason: score.FuOpenTerminalPon},
			{Fu: 2, Reason: score.FuKanchan},
			{Fu: 2, Reason: score.FuValuedPair},
			{Fu: 2, Reason: score.FuOpenPon},
		},
	})
}

func TestEstimateHandValue_WhenOpenHandWinsOnPairOfSplitQuad_ShouldScore30Fu(t *testing.T) {
	melds := []meld.Meld{chi(t, "123m")}

	got := handValue(t, "11112233444m555p", "1m", melds, handWonBy(score.WinHoutei))
	if han, ok := got.Value.(play.Han); !ok || han.Fu != 30 {
		t.Errorf("EstimateHandValue(11112233444m555p, 1m).Value = %+v, want 30 fu", got.Value)
	}
}

func TestEstimateHandValue_WhenRiichiPinfuTsumo_ShouldScore3Han20Fu(t *testing.T) {
	got := handValue(t, "234789m12345666p", "6p", nil, withRiichi(tsumo()))
	handWantValue(t, "EstimateHandValue(234789m12345666p, 6p)", got, score.HandValue{
		Value:   play.Han{Han: 3, Fu: 20},
		Payment: play.TsumoPayment{Dealer: 1300, NonDealer: 700},
		Total:   2700,
		Yaku: []score.Yaku{
			{ID: play.YakuTsumo, Han: 1},
			{ID: play.YakuRiichi, Han: 1},
			{ID: play.YakuPinfu, Han: 1},
		},
		FuDetails: []score.FuDetail{{Fu: 20, Reason: score.FuBase}},
	})
}

func TestEstimateHandValue_WhenClosedTanyaoRon_ShouldScore1Han40Fu(t *testing.T) {
	got := handValue(t, "22444m333567p444s", "4s", nil, ron())
	handWantValue(t, "EstimateHandValue(22444m333567p444s, 4s)", got, score.HandValue{
		Value:   play.Han{Han: 1, Fu: 40},
		Payment: play.RonPayment{Discarder: 1300},
		Total:   1300,
		Yaku:    []score.Yaku{{ID: play.YakuTanyao, Han: 1}},
		FuDetails: []score.FuDetail{
			{Fu: 30, Reason: score.FuBase},
			{Fu: 4, Reason: score.FuClosedPon},
			{Fu: 4, Reason: score.FuClosedPon},
			{Fu: 2, Reason: score.FuOpenPon},
		},
	})
}

func TestEstimateHandValue_WhenOpenHandHoldsDoraAndAkaDora_ShouldScoreMangan(t *testing.T) {
	melds := []meld.Meld{pon(t, "555z")}
	dora := score.Dora{Indicators: tiles(t, "6m1p")}

	got, err := valueOf(t, "234067m22p234s555z", "7m", melds, ron(), dora, defaultRules())
	if err != nil {
		t.Fatalf("EstimateHandValue(234067m22p234s555z, 7m) error = %v", err)
	}

	handWantValue(t, "EstimateHandValue(234067m22p234s555z, 7m)", got, score.HandValue{
		Value:     play.Han{Han: 5, Fu: 30},
		Limit:     play.Some(play.LimitMangan),
		Payment:   play.RonPayment{Discarder: 8000},
		Total:     8000,
		Yaku:      []score.Yaku{{ID: play.YakuHaku, Han: 1}},
		Dora:      play.DoraCount{Dora: 3, AkaDora: 1},
		FuDetails: []score.FuDetail{{Fu: 20, Reason: score.FuBase}, {Fu: 4, Reason: score.FuOpenTerminalPon}},
	})
}

func TestEstimateHandValue_WhenUraIndicatorsGiven_ShouldCountUraDoraOnlyWithRiichi(t *testing.T) {
	dora := score.Dora{Indicators: tiles(t, "3s"), UraIndicators: tiles(t, "5p")}
	estimateWith := func(situation score.Situation) score.HandValue {
		value, err := valueOf(t, handPlain, "4s", nil, situation, dora, defaultRules())
		if err != nil {
			t.Fatalf("EstimateHandValue(%+v) error = %v", situation, err)
		}

		return value
	}

	riichi := estimateWith(withRiichi(ron()))
	tsumoWin := estimateWith(tsumo())
	if ids := yakuIDs(riichi); !reflect.DeepEqual(ids, []play.YakuID{play.YakuRiichi}) {
		t.Errorf("EstimateHandValue(riichi ron).Yaku = %v, want [%v]", ids, play.YakuRiichi)
	}
	if want := (play.DoraCount{Dora: 3, UraDora: 2}); riichi.Dora != want {
		t.Errorf("EstimateHandValue(riichi ron).Dora = %+v, want %+v", riichi.Dora, want)
	}
	if want := (play.Han{Han: 6, Fu: 40}); riichi.Value != want {
		t.Errorf("EstimateHandValue(riichi ron).Value = %+v, want %+v", riichi.Value, want)
	}
	if want := play.Some(play.LimitHaneman); riichi.Limit != want {
		t.Errorf("EstimateHandValue(riichi ron).Limit = %+v, want %+v", riichi.Limit, want)
	}
	if want := (play.RonPayment{Discarder: 12000}); riichi.Payment != want || riichi.Total != 12000 {
		t.Errorf("EstimateHandValue(riichi ron) payment, total = %+v, %d, want %+v, 12000",
			riichi.Payment, riichi.Total, want)
	}

	if ids := yakuIDs(tsumoWin); !reflect.DeepEqual(ids, []play.YakuID{play.YakuTsumo}) {
		t.Errorf("EstimateHandValue(tsumo).Yaku = %v, want [%v]", ids, play.YakuTsumo)
	}
	if want := (play.DoraCount{Dora: 3}); tsumoWin.Dora != want {
		t.Errorf("EstimateHandValue(tsumo).Dora = %+v, want %+v", tsumoWin.Dora, want)
	}
	if want := (play.Han{Han: 4, Fu: 30}); tsumoWin.Value != want {
		t.Errorf("EstimateHandValue(tsumo).Value = %+v, want %+v", tsumoWin.Value, want)
	}
	if tsumoWin.Limit.OK {
		t.Errorf("EstimateHandValue(tsumo).Limit = %+v, want absent", tsumoWin.Limit)
	}
	if want := (play.TsumoPayment{Dealer: 3900, NonDealer: 2000}); tsumoWin.Payment != want || tsumoWin.Total != 7900 {
		t.Errorf("EstimateHandValue(tsumo) payment, total = %+v, %d, want %+v, 7900",
			tsumoWin.Payment, tsumoWin.Total, want)
	}
}

func TestEstimateHandValue_WhenKokushi_ShouldScoreDoubleOnThirteenSidedWaitAndSingleOtherwise(t *testing.T) {
	thirteenSided := handValue(t, handKokushi, "1s", nil, ron())
	single := handValue(t, handKokushi, "7z", nil, handDealerWonBy(score.WinTsumo))
	handWantValue(t, "EstimateHandValue(kokushi on 1s)", thirteenSided, score.HandValue{
		Value:     play.Yakuman{Count: 2},
		Limit:     play.Some(play.LimitYakuman),
		Payment:   play.RonPayment{Discarder: 64000},
		Total:     64000,
		Yaku:      []score.Yaku{{ID: play.YakuDaburuKokushiMusou, Han: 26}},
		FuDetails: []score.FuDetail{},
	})
	if ids := yakuIDs(single); !reflect.DeepEqual(ids, []play.YakuID{play.YakuKokushiMusou}) {
		t.Errorf("EstimateHandValue(kokushi on 7z).Yaku = %v, want [%v]", ids, play.YakuKokushiMusou)
	}
	if want := (play.Yakuman{Count: 1}); single.Value != want {
		t.Errorf("EstimateHandValue(kokushi on 7z).Value = %+v, want %+v", single.Value, want)
	}
	if want := (play.DealerTsumoPayment{NonDealer: 16000}); single.Payment != want || single.Total != 48000 {
		t.Errorf("EstimateHandValue(kokushi on 7z) payment, total = %+v, %d, want %+v, 48000",
			single.Payment, single.Total, want)
	}
}

func TestEstimateHandValue_WhenKokushiRonOnFirstTurn_ShouldScoreDoubleKokushi(t *testing.T) {
	got := handValue(t, handKokushi, "1s", nil, handOnFirstTurn(ron()))
	if ids := yakuIDs(got); !reflect.DeepEqual(ids, []play.YakuID{play.YakuDaburuKokushiMusou}) {
		t.Errorf("EstimateHandValue(first-turn kokushi).Yaku = %v, want [%v]", ids, play.YakuDaburuKokushiMusou)
	}
	if want := (play.Yakuman{Count: 2}); got.Value != want {
		t.Errorf("EstimateHandValue(first-turn kokushi).Value = %+v, want %+v", got.Value, want)
	}
	if want := play.Some(play.LimitYakuman); got.Limit != want {
		t.Errorf("EstimateHandValue(first-turn kokushi).Limit = %+v, want %+v", got.Limit, want)
	}
	if want := (play.RonPayment{Discarder: 64000}); got.Payment != want {
		t.Errorf("EstimateHandValue(first-turn kokushi).Payment = %+v, want %+v", got.Payment, want)
	}
}

func TestEstimateHandValue_WhenDoubleYakumanTurnedOff_ShouldScoreSingleYakuman(t *testing.T) {
	suuankou := "111333m555p777s22z"
	situation := score.Situation{Win: score.WinTsumo, SeatWind: tile.West, RoundWind: tile.North}
	singleRules := defaultRules()
	singleRules.DoubleYakuman = false

	double := handValue(t, suuankou, "2z", nil, situation)
	single, singleErr := valueOf(t, suuankou, "2z", nil, situation, score.Dora{}, singleRules)
	kokushi, kokushiErr := valueOf(t, handKokushi, "1s", nil, ron(), score.Dora{}, singleRules)
	if singleErr != nil || kokushiErr != nil {
		t.Fatalf("EstimateHandValue(single yakuman rules) errors = %v, %v", singleErr, kokushiErr)
	}

	if want := (play.Yakuman{Count: 2, Fu: play.Some(50)}); double.Value != want {
		t.Errorf("EstimateHandValue(suuankou tanki).Value = %+v, want %+v", double.Value, want)
	}
	if want := play.Some(play.LimitYakuman); double.Limit != want {
		t.Errorf("EstimateHandValue(suuankou tanki).Limit = %+v, want %+v", double.Limit, want)
	}
	if want := (play.TsumoPayment{Dealer: 32000, NonDealer: 16000}); double.Payment != want || double.Total != 64000 {
		t.Errorf("EstimateHandValue(suuankou tanki) payment, total = %+v, %d, want %+v, 64000",
			double.Payment, double.Total, want)
	}
	handWantValue(t, "EstimateHandValue(suuankou tanki, single yakuman)", single, score.HandValue{
		Value:   play.Yakuman{Count: 1, Fu: play.Some(50)},
		Limit:   play.Some(play.LimitYakuman),
		Payment: play.TsumoPayment{Dealer: 16000, NonDealer: 8000},
		Total:   32000,
		Yaku:    []score.Yaku{{ID: play.YakuSuuankouTanki, Han: 13}},
		FuDetails: []score.FuDetail{
			{Fu: 20, Reason: score.FuBase},
			{Fu: 8, Reason: score.FuClosedTerminalPon},
			{Fu: 4, Reason: score.FuClosedPon},
			{Fu: 4, Reason: score.FuClosedPon},
			{Fu: 4, Reason: score.FuClosedPon},
			{Fu: 2, Reason: score.FuPairWait},
			{Fu: 2, Reason: score.FuTsumo},
		},
	})
	if want := (play.Yakuman{Count: 1}); kokushi.Value != want {
		t.Errorf("EstimateHandValue(kokushi on 1s, single yakuman).Value = %+v, want %+v", kokushi.Value, want)
	}
	if want := (play.RonPayment{Discarder: 32000}); kokushi.Payment != want || kokushi.Total != 32000 {
		t.Errorf("EstimateHandValue(kokushi on 1s, single yakuman) payment, total = %+v, %d, want %+v, 32000",
			kokushi.Payment, kokushi.Total, want)
	}
}

func TestNagashiMangan_WhenDealer_ShouldTakeAManganTsumoFromEach(t *testing.T) {
	got := score.NagashiMangan(tile.East)
	if want := (play.DealerTsumoPayment{NonDealer: 4000}); got != want {
		t.Errorf("NagashiMangan(East) = %+v, want %+v", got, want)
	}
	if got.Sum() != 12000 {
		t.Errorf("NagashiMangan(East).Sum() = %d, want 12000", got.Sum())
	}
}

func TestNagashiMangan_WhenNonDealer_ShouldTakeAManganTsumoFromEach(t *testing.T) {
	for _, wind := range []tile.Wind{tile.South, tile.West, tile.North} {
		t.Run(fmt.Sprint(wind), func(t *testing.T) {
			got := score.NagashiMangan(wind)
			if want := (play.TsumoPayment{Dealer: 4000, NonDealer: 2000}); got != want {
				t.Errorf("NagashiMangan(%d) = %+v, want %+v", wind, got, want)
			}
			if got.Sum() != 8000 {
				t.Errorf("NagashiMangan(%d).Sum() = %d, want 8000", wind, got.Sum())
			}
		})
	}
}

func handWantTsumo30FuWithWait(tb testing.TB, call string, got score.HandValue, wait score.FuReason) {
	tb.Helper()
	handWantValue(tb, call, got, score.HandValue{
		Value:   play.Han{Han: 1, Fu: 30},
		Payment: play.TsumoPayment{Dealer: 500, NonDealer: 300},
		Total:   1100,
		Yaku:    []score.Yaku{{ID: play.YakuTsumo, Han: 1}},
		FuDetails: []score.FuDetail{
			{Fu: 20, Reason: score.FuBase},
			{Fu: 4, Reason: score.FuClosedPon},
			{2, wait},
			{Fu: 2, Reason: score.FuTsumo},
		},
	})
}

func TestEstimateHandValue_WhenReadingsRoundToEqualFu_ShouldPickMoreUnroundedFu(t *testing.T) {
	got := handValue(t, "23444m567p789p555s", "4m", nil, tsumo())
	handWantTsumo30FuWithWait(t, "EstimateHandValue(23444m567p789p555s, 4m)", got, score.FuPairWait)
}

func TestEstimateHandValue_WhenReadingsFullyTie_ShouldPickFirstReading(t *testing.T) {
	got := handValue(t, "34445m567p789p555s", "4m", nil, tsumo())
	handWantTsumo30FuWithWait(t, "EstimateHandValue(34445m567p789p555s, 4m)", got, score.FuKanchan)
}

func handTilesFrom136(tb testing.TB, ids []int, aka tile.AkaDora) []tile.Tile {
	tb.Helper()
	read := make([]tile.Tile, 0, len(ids))
	for _, n := range ids {
		id, ok := tile.NewTileID(n)
		if !ok {
			tb.Fatalf("NewTileID(%d) = false, want a tile id", n)
		}

		read = append(read, id.Tile(aka))
	}

	return read
}

func TestEstimateHandValue_WhenTilesReadFrom136IDs_ShouldCountRedFiveOnlyWithAkaDora(t *testing.T) {
	idsWithID52 := []int{4, 5, 12, 13, 14, 44, 45, 46, 52, 56, 60, 84, 85}
	valueFrom136 := func(aka tile.AkaDora) (score.HandValue, error) {
		h := score.Hand{
			Concealed: handTilesFrom136(t, idsWithID52, aka),
			WinTile:   handTilesFrom136(t, []int{86}, aka)[0],
		}
		return score.EstimateHandValue(h, ron(), score.Dora{}, defaultRules())
	}

	plain, plainErr := valueFrom136(tile.AkaDoraDisabled)
	direct, directErr := handEstimate(t, "22444m333567p444s", "4s", nil, ron())
	red, redErr := valueFrom136(tile.AkaDoraEnabled)
	if plainErr != nil || directErr != nil || redErr != nil {
		t.Fatalf("EstimateHandValue(136 ids) errors = %v, %v, %v", plainErr, directErr, redErr)
	}

	handWantValue(t, "EstimateHandValue(136 ids, aka dora disabled)", plain, direct)
	if want := (play.Han{Han: 1, Fu: 40}); plain.Value != want || plain.Dora.AkaDora != 0 {
		t.Errorf("EstimateHandValue(136 ids, aka dora disabled) value, aka dora = %+v, %d, want %+v, 0",
			plain.Value, plain.Dora.AkaDora, want)
	}
	if want := (play.Han{Han: 2, Fu: 40}); red.Value != want || red.Dora.AkaDora != 1 {
		t.Errorf("EstimateHandValue(136 ids, aka dora enabled) value, aka dora = %+v, %d, want %+v, 1",
			red.Value, red.Dora.AkaDora, want)
	}
}
