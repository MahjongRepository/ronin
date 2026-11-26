package score_test

import (
	"errors"
	"fmt"
	"reflect"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const yakuHand = "234456m66p123444s"

type yakuSummary struct {
	Value play.Value
	Yaku  []play.YakuID
	Dora  play.DoraCount
}

type yakuCase struct {
	hand      string
	winTile   string
	melds     []meld.Meld
	situation score.Situation
	dora      score.Dora
	want      yakuSummary
	wantErr   error
}

func yakuSummaryOf(value score.HandValue) yakuSummary {
	return yakuSummary{Value: value.Value, Yaku: yakuIDs(value), Dora: value.Dora}
}

func yakuCheckCases(t *testing.T, rules score.Rules, cases ...yakuCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.hand+" on "+c.winTile, func(t *testing.T) {
			value, err := valueOf(t, c.hand, c.winTile, c.melds, c.situation, c.dora, rules)
			if c.wantErr != nil {
				if !errors.Is(err, c.wantErr) {
					t.Errorf("EstimateHandValue(%s on %s) error = %v, want %v", c.hand, c.winTile, err, c.wantErr)
				}

				return
			}

			got := yakuSummaryOf(value)
			if err != nil || !reflect.DeepEqual(got, c.want) {
				t.Errorf("EstimateHandValue(%s on %s) = %+v, %v, want %+v", c.hand, c.winTile, got, err, c.want)
			}
		})
	}
}

func yakuHan(han, fu int, yaku ...play.YakuID) yakuSummary {
	return yakuSummary{Value: play.Han{Han: han, Fu: fu}, Yaku: yaku}
}

func yakuHanWithDora(han, fu int, dora play.DoraCount, yaku ...play.YakuID) yakuSummary {
	return yakuSummary{Value: play.Han{Han: han, Fu: fu}, Yaku: yaku, Dora: dora}
}

func yakuIndicators(t *testing.T, mpsz string) score.Dora {
	t.Helper()
	return score.Dora{Indicators: tiles(t, mpsz)}
}

func yakuWinds(seatWind, roundWind tile.Wind) score.Situation {
	return score.Situation{Win: score.WinRon, SeatWind: seatWind, RoundWind: roundWind}
}

func yakuWith(situation score.Situation, win score.Win) score.Situation {
	situation.Win = win
	return situation
}

func yakuMustValue(
	t *testing.T,
	wholeHand, winTile string,
	melds []meld.Meld,
	situation score.Situation,
	dora score.Dora,
	rules score.Rules,
) score.HandValue {
	t.Helper()
	value, err := valueOf(t, wholeHand, winTile, melds, situation, dora, rules)
	if err != nil {
		t.Fatalf("EstimateHandValue(%s on %s) error = %v", wholeHand, winTile, err)
	}

	return value
}

func yakuSeatWindCases(honor string, wind, otherRoundWind tile.Wind, seatYaku, roundYaku play.YakuID) []yakuCase {
	hand := "23422m234567s" + honor + honor + honor + "z"
	winTile := honor + "z"

	return []yakuCase{
		{
			hand: hand, winTile: winTile, situation: yakuWinds(wind, otherRoundWind),
			want: yakuHan(1, 40, seatYaku),
		},
		{
			hand: hand, winTile: winTile, situation: yakuWinds(wind, wind),
			want: yakuHan(2, 40, seatYaku, roundYaku),
		},
	}
}

func TestEstimateHandValue_WhenHandIsClosed_ShouldScoreItsYakuAndFu(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "11m123345p678s666z", winTile: "3p", situation: tsumo(),
			want: yakuHan(2, 40, play.YakuTsumo, play.YakuHatsu),
		},
		yakuCase{hand: "234789m12345666p", winTile: "6p", situation: ron(), want: yakuHan(1, 30, play.YakuPinfu)},
		yakuCase{
			hand: "34555789p678s555z", winTile: "5p", situation: tsumo(),
			want: yakuHan(2, 40, play.YakuTsumo, play.YakuHaku),
		},
		yakuCase{hand: "678m88p123345678s", winTile: "3s", situation: ron(), want: yakuHan(1, 30, play.YakuPinfu)},
		yakuCase{hand: "123456m456p12399s", winTile: "1s", situation: ron(), want: yakuHan(1, 30, play.YakuPinfu)},
		yakuCase{
			hand: "456m12367778p678s", winTile: "7p", situation: withRiichi(ron()),
			want: yakuHan(1, 40, play.YakuRiichi),
		},
		yakuCase{
			hand: "345m999p67778s222z", winTile: "7s",
			situation: yakuWith(yakuWinds(tile.West, tile.North), score.WinTsumo),
			want:      yakuHan(1, 40, play.YakuTsumo),
		},
		yakuCase{
			hand: "345m33445577789s", winTile: "7s", situation: tsumo(),
			want: yakuHan(2, 30, play.YakuTsumo, play.YakuIipeikou),
		},
		yakuCase{hand: "12333456789m345s", winTile: "3m", situation: ron(), want: yakuHan(2, 40, play.YakuIttsu)},
		yakuCase{hand: "567m12333345p555z", winTile: "3p", situation: ron(), want: yakuHan(1, 40, play.YakuHaku)},
		yakuCase{
			hand: "567p3334444555s77z", winTile: "3s", melds: []meld.Meld{closedKan(t, "4444s")},
			situation: withRiichi(ron()), want: yakuHan(1, 60, play.YakuRiichi),
		},
	)
}

func TestEstimateHandValue_WhenHandIsOpen_ShouldScoreItsYakuFuAndDora(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "112233999p11177z", winTile: "9p",
			melds:     []meld.Meld{pon(t, "111z"), chi(t, "123p"), chi(t, "123p")},
			situation: yakuWinds(tile.West, tile.South),
			want:      yakuHan(3, 30, play.YakuChantai, play.YakuHonitsu),
		},
		yakuCase{
			hand: "22244456799p4444z", winTile: "2p", melds: []meld.Meld{openKan(t, "4444z")},
			situation: ron(), dora: yakuIndicators(t, "3s3z"),
			want: yakuHanWithDora(6, 50, play.DoraCount{Dora: 4}, play.YakuHonitsu),
		},
		yakuCase{
			hand: "111123666789s11z", winTile: "1s", melds: []meld.Meld{pon(t, "666s")},
			situation: yakuWinds(tile.East, tile.South), dora: yakuIndicators(t, "4z"),
			want: yakuHanWithDora(4, 40, play.DoraCount{Dora: 2}, play.YakuHonitsu),
		},
		yakuCase{
			hand: "12333p567s666777z", winTile: "3p", melds: []meld.Meld{pon(t, "666z"), pon(t, "777z")},
			situation: ron(), want: yakuHan(2, 30, play.YakuHatsu, play.YakuChun),
		},
		yakuCase{
			hand: "11156677899m7777z", winTile: "7m",
			melds:     []meld.Meld{openKan(t, "7777z"), pon(t, "111m"), chi(t, "678m")},
			situation: ron(), want: yakuHan(3, 40, play.YakuChun, play.YakuHonitsu),
		},
	)
}

func TestEstimateHandValue_WhenOpenHandIsFlushOrYakuhai_ShouldScoreTheOpenHan(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "122223777888m66z", winTile: "2m", melds: []meld.Meld{chi(t, "123m"), pon(t, "777m")},
			situation: ron(), want: yakuHan(2, 30, play.YakuHonitsu),
		},
		yakuCase{
			hand: "11144678888p444z", winTile: "8p",
			melds:     []meld.Meld{pon(t, "444z"), pon(t, "111p"), pon(t, "888p")},
			situation: ron(), want: yakuHan(2, 30, play.YakuHonitsu),
		},
		yakuCase{
			hand: "112233667788p22z", winTile: "3p", melds: []meld.Meld{chi(t, "123p")},
			situation: yakuWinds(tile.West, tile.North), want: yakuHan(2, 30, play.YakuHonitsu),
		},
		yakuCase{
			hand: "11123456777888s", winTile: "4s",
			melds:     []meld.Meld{chi(t, "123s"), pon(t, "777s"), pon(t, "888s")},
			situation: tsumo(), want: yakuHan(5, 30, play.YakuChinitsu),
		},
		yakuCase{
			hand: "112233789s55777z", winTile: "2s", melds: []meld.Meld{chi(t, "123s")},
			situation: ron(), want: yakuHan(4, 40, play.YakuChun, play.YakuChantai, play.YakuHonitsu),
		},
		yakuCase{
			hand: "234777888999p22z", winTile: "9p", melds: []meld.Meld{chi(t, "234p"), chi(t, "789p")},
			situation: yakuWinds(tile.West, tile.North), want: yakuHan(2, 30, play.YakuHonitsu),
		},
		yakuCase{
			hand: "444m77888899p777z", winTile: "8p", melds: []meld.Meld{pon(t, "777z"), pon(t, "444m")},
			situation: tsumo(), want: yakuHan(1, 30, play.YakuChun),
		},
		yakuCase{
			hand: "34567777889p555z", winTile: "7p", melds: []meld.Meld{chi(t, "345p")},
			situation: ron(), want: yakuHan(3, 30, play.YakuHaku, play.YakuHonitsu),
		},
	)
}

func TestEstimateHandValue_WhenChiTilesComeInAnyOrder_ShouldScoreTheSame(t *testing.T) {
	concealed := tiles(t, "234567m99s55z")
	chiTiles := tiles(t, "789p")
	want := yakuHan(1, 30, play.YakuHaku)

	for _, order := range [][3]int{{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}} {
		t.Run(fmt.Sprint(order), func(t *testing.T) {
			m, err := meld.NewChi([3]tile.Tile{chiTiles[order[0]], chiTiles[order[1]], chiTiles[order[2]]})
			if err != nil {
				t.Fatalf("NewChi(%v) error = %v", order, err)
			}

			h := score.Hand{Concealed: concealed, WinTile: oneTile(t, "5z"), Melds: []meld.Meld{m}}

			value, err := score.EstimateHandValue(h, ron(), score.Dora{}, defaultRules())

			got := yakuSummaryOf(value)
			if err != nil || !reflect.DeepEqual(got, want) {
				t.Errorf("EstimateHandValue(chi in order %v) = %+v, %v, want %+v", order, got, err, want)
			}
		})
	}
}

func TestEstimateHandValue_WhenRiichiRon_ShouldScoreRiichi(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: yakuHand, winTile: "4s", situation: withRiichi(ron()), want: yakuHan(1, 40, play.YakuRiichi),
	})
}

func TestEstimateHandValue_WhenTsumo_ShouldScoreMenzenTsumoOnlyWhenClosed(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: yakuHand, winTile: "4s", situation: tsumo(), want: yakuHan(1, 30, play.YakuTsumo)},
		yakuCase{
			hand: yakuHand, winTile: "4s", melds: []meld.Meld{chi(t, "123s")}, situation: tsumo(),
			wantErr: score.NoYakuError{},
		},
	)
}

func TestEstimateHandValue_WhenRiichiIsIppatsu_ShouldAddIppatsu(t *testing.T) {
	situation := ron()
	situation.Riichi = play.Some(play.Riichi{Ippatsu: true})

	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: yakuHand, winTile: "4s", situation: situation,
		want: yakuHan(2, 40, play.YakuRiichi, play.YakuIppatsu),
	})
}

func TestEstimateHandValue_WhenRinshanWin_ShouldAddTsumoOnlyWithClosedKan(t *testing.T) {
	hand := "234456m66p1234444s"
	situation := yakuWith(ron(), score.WinRinshan)

	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: hand, winTile: "1s", melds: []meld.Meld{closedKan(t, "4444s")}, situation: situation,
			want: yakuHan(2, 40, play.YakuTsumo, play.YakuRinshan),
		},
		yakuCase{
			hand: hand, winTile: "1s", melds: []meld.Meld{openKan(t, "4444s")}, situation: situation,
			want: yakuHan(1, 30, play.YakuRinshan),
		},
	)
}

func TestEstimateHandValue_WhenChankanWin_ShouldScoreChankan(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: yakuHand, winTile: "1s", situation: yakuWith(ron(), score.WinChankan),
		want: yakuHan(1, 40, play.YakuChankan),
	})
}

func TestEstimateHandValue_WhenHaiteiWin_ShouldAddTsumoOnlyWhenClosed(t *testing.T) {
	situation := yakuWith(ron(), score.WinHaitei)

	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: yakuHand, winTile: "4s", situation: situation,
			want: yakuHan(2, 30, play.YakuTsumo, play.YakuHaitei),
		},
		yakuCase{
			hand: yakuHand, winTile: "4s", melds: []meld.Meld{chi(t, "123s")}, situation: situation,
			want: yakuHan(1, 30, play.YakuHaitei),
		},
	)
}

func TestEstimateHandValue_WhenHouteiWin_ShouldScoreHoutei(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: yakuHand, winTile: "4s", situation: yakuWith(ron(), score.WinHoutei),
		want: yakuHan(1, 40, play.YakuHoutei),
	})
}

func TestEstimateHandValue_WhenNonDealerRonsOnFirstTurn_ShouldHaveNoYaku(t *testing.T) {
	situation := ron()
	situation.FirstTurn = true

	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: yakuHand, winTile: "4s", situation: situation, wantErr: score.NoYakuError{},
	})
}

func TestEstimateHandValue_WhenRiichiIsDouble_ShouldScoreDaburuRiichiAlone(t *testing.T) {
	situation := ron()
	situation.Riichi = play.Some(play.Riichi{Double: true})

	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: yakuHand, winTile: "4s", situation: situation, want: yakuHan(2, 40, play.YakuDaburuRiichi),
	})
}

func TestEstimateHandValue_WhenSevenPairs_ShouldScoreChiitoitsuAt25Fu(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "113355m11p113355s", winTile: "1p", situation: ron(), want: yakuHan(2, 25, play.YakuChiitoitsu),
	})
}

func TestEstimateHandValue_WhenSevenPairsRepeatAPair_ShouldNotWin(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "1133m11p11335555s", winTile: "1p", situation: ron(), wantErr: score.NotWinningError{},
	})
}

func TestEstimateHandValue_WhenAllSimples_ShouldScoreOpenTanyaoOnlyUnderItsRule(t *testing.T) {
	hand := "234567m22p234567s"
	melds := []meld.Meld{chi(t, "234s")}
	openTanyao := defaultRules()
	openTanyao.OpenTanyao = true

	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: hand, winTile: "7m", situation: withRiichi(ron()),
			want: yakuHan(3, 30, play.YakuRiichi, play.YakuPinfu, play.YakuTanyao),
		},
		yakuCase{hand: hand, winTile: "7m", melds: melds, situation: ron(), wantErr: score.NoYakuError{}},
	)

	yakuCheckCases(t, openTanyao, yakuCase{
		hand: hand, winTile: "7m", melds: melds, situation: ron(), want: yakuHan(1, 30, play.YakuTanyao),
	})
}

func TestEstimateHandValue_WhenClosedRyanmenHandHasNoFu_ShouldScorePinfu(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: "123456m55p123456s", winTile: "6m", situation: ron(), want: yakuHan(1, 30, play.YakuPinfu)},
		yakuCase{hand: "123555m55p123456s", winTile: "5m", situation: ron(), wantErr: score.NoYakuError{}},
		yakuCase{hand: "123456m55p111456s", winTile: "6m", situation: ron(), wantErr: score.NoYakuError{}},
		yakuCase{hand: "123456m55p123456s", winTile: "3s", situation: ron(), wantErr: score.NoYakuError{}},
		yakuCase{hand: "123456m55p123567s", winTile: "6s", situation: ron(), wantErr: score.NoYakuError{}},
		yakuCase{hand: "22456678m123678p", winTile: "2m", situation: ron(), wantErr: score.NoYakuError{}},
		yakuCase{
			hand: "123456m123678s11z", winTile: "6s", situation: yakuWinds(tile.East, tile.West),
			wantErr: score.NoYakuError{},
		},
		yakuCase{
			hand: "123456m123678s22z", winTile: "6s", situation: yakuWinds(tile.West, tile.North),
			want: yakuHan(1, 30, play.YakuPinfu),
		},
		yakuCase{
			hand: "123456m456p12399s", winTile: "1m", melds: []meld.Meld{chi(t, "123s")}, situation: ron(),
			wantErr: score.NoYakuError{},
		},
	)
}

func TestEstimateHandValue_WhenPinfuTsumoTakesFu_ShouldDropPinfu(t *testing.T) {
	rules := defaultRules()
	rules.FuForPinfuTsumo = true

	yakuCheckCases(t, rules, yakuCase{
		hand: "123456m55p123456s", winTile: "6m", situation: tsumo(), want: yakuHan(1, 30, play.YakuTsumo),
	})
}

func TestEstimateHandValue_WhenTwoIdenticalSequences_ShouldScoreIipeikouOnlyClosed(t *testing.T) {
	hand := "333m12344p112233s"

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "3m", situation: ron(), want: yakuHan(1, 40, play.YakuIipeikou)},
		yakuCase{
			hand: hand, winTile: "3m", melds: []meld.Meld{chi(t, "123s")}, situation: ron(),
			wantErr: score.NoYakuError{},
		},
	)
}

func TestEstimateHandValue_WhenTwoIipeikou_ShouldScoreRyanpeikouOnlyClosed(t *testing.T) {
	hand := "33m223344p112233s"

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "3p", situation: ron(), want: yakuHan(3, 40, play.YakuRyanpeikou)},
		yakuCase{
			hand: hand, winTile: "3p", melds: []meld.Meld{chi(t, "123s")}, situation: ron(),
			wantErr: score.NoYakuError{},
		},
	)
}

func TestEstimateHandValue_WhenSameSequenceInEverySuit_ShouldScoreSanshokuLessWhenOpen(t *testing.T) {
	hand := "12399m123p123456s"

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "2m", situation: ron(), want: yakuHan(2, 40, play.YakuSanshoku)},
		yakuCase{
			hand: hand, winTile: "2m", melds: []meld.Meld{chi(t, "123s")}, situation: ron(),
			want: yakuHan(1, 30, play.YakuSanshoku),
		},
	)
}

func TestEstimateHandValue_WhenSamePonInEverySuit_ShouldScoreSanshokuDoukou(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "222m22245699p222s", winTile: "9p", melds: []meld.Meld{pon(t, "222s")}, situation: ron(),
		want: yakuHan(2, 40, play.YakuSanshokuDoukou),
	})
}

func TestEstimateHandValue_WhenSanshokuDoukouHoldsAKan_ShouldScoreSanshokuDoukou(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "222m22245699p2222s", winTile: "9p", melds: []meld.Meld{openKan(t, "2222s")}, situation: ron(),
		want: yakuHan(2, 40, play.YakuSanshokuDoukou),
	})
}

func TestEstimateHandValue_WhenAllPons_ShouldScoreToitoi(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "333m44555p111333s", winTile: "5p", melds: []meld.Meld{pon(t, "111s"), pon(t, "333s")},
			situation: ron(), want: yakuHan(2, 40, play.YakuToitoi),
		},
		yakuCase{
			hand: "777888999p777s44z", winTile: "9p", melds: []meld.Meld{pon(t, "777s")},
			situation: ron(), want: yakuHan(2, 40, play.YakuToitoi),
		},
	)
}

func TestEstimateHandValue_WhenThreeKans_ShouldScoreSankantsu(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "123m446666p11113333s", winTile: "3m",
		melds:     []meld.Meld{openKan(t, "1111s"), openKan(t, "3333s"), openKan(t, "6666p")},
		situation: ron(), want: yakuHan(2, 60, play.YakuSankantsu),
	})
}

func TestEstimateHandValue_WhenAllTerminalsAndHonors_ShouldScoreHonroutou(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "111m111999s11222z", winTile: "2z", melds: []meld.Meld{pon(t, "111s")},
			situation: yakuWinds(tile.West, tile.North),
			want:      yakuHan(4, 50, play.YakuHonroutou, play.YakuToitoi),
		},
		yakuCase{
			hand: "1199m11p22334466z", winTile: "1m", situation: ron(),
			want: yakuHan(4, 25, play.YakuHonroutou, play.YakuChiitoitsu),
		},
	)
}

func TestEstimateHandValue_WhenThreeConcealedPonsOnTsumo_ShouldScoreSanankou(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "333m44555p123444s", winTile: "5p", melds: []meld.Meld{chi(t, "123s")}, situation: tsumo(),
		want: yakuHan(2, 40, play.YakuSanankou),
	})
}

func TestEstimateHandValue_WhenRonCompletesAPon_ShouldCountItOpenUnlessAClosedChiHoldsTheTile(t *testing.T) {
	hand := "111444m777p234s55z"
	riichiRon := withRiichi(ron())

	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: hand, winTile: "4s", situation: riichiRon,
			want: yakuHan(3, 50, play.YakuRiichi, play.YakuSanankou),
		},
		yakuCase{hand: hand, winTile: "4m", situation: riichiRon, want: yakuHan(1, 50, play.YakuRiichi)},
		yakuCase{
			hand: hand, winTile: "4m", situation: withRiichi(tsumo()),
			want: yakuHan(4, 40, play.YakuTsumo, play.YakuRiichi, play.YakuSanankou),
		},
		yakuCase{
			hand: hand, winTile: "5z", situation: riichiRon,
			want: yakuHan(3, 50, play.YakuRiichi, play.YakuSanankou),
		},
		yakuCase{
			hand: "444m222234s55777z", winTile: "2s", melds: []meld.Meld{chi(t, "234s")}, situation: ron(),
			want: yakuHan(1, 40, play.YakuChun),
		},
	)

	value := yakuMustValue(t, "444m777p222234s55z", "2s", nil, riichiRon, score.Dora{}, defaultRules())

	got := yakuSummaryOf(value)
	want := yakuHan(3, 50, play.YakuRiichi, play.YakuSanankou)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("EstimateHandValue(444m777p222234s55z on 2s) = %+v, want %+v", got, want)
	}

	wantFu := []score.FuDetail{
		{Fu: 30, Reason: score.FuBase},
		{Fu: 4, Reason: score.FuClosedPon},
		{Fu: 4, Reason: score.FuClosedPon},
		{Fu: 4, Reason: score.FuClosedPon},
		{Fu: 2, Reason: score.FuValuedPair},
	}
	if !reflect.DeepEqual(value.FuDetails, wantFu) {
		t.Errorf("EstimateHandValue(444m777p222234s55z on 2s).FuDetails = %+v, want %+v", value.FuDetails, wantFu)
	}
}

func TestEstimateHandValue_WhenKanIsOneOfThreePons_ShouldCountClosedKanForSanankouButNotOpenKan(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "1111444m777p234s55z", winTile: "3s", melds: []meld.Meld{closedKan(t, "1111m")},
			situation: withRiichi(tsumo()),
			want:      yakuHan(4, 70, play.YakuTsumo, play.YakuRiichi, play.YakuSanankou),
		},
		yakuCase{
			hand: "1111444m234s55777z", winTile: "3s", melds: []meld.Meld{openKan(t, "1111m")},
			situation: tsumo(), want: yakuHan(1, 60, play.YakuChun),
		},
	)
}

func TestEstimateHandValue_WhenRonTileFitsAClosedChiAndAClosedPon_ShouldKeepSanankou(t *testing.T) {
	value := yakuMustValue(
		t, "444789999p22333z", "9p", nil, yakuWinds(tile.North, tile.East), score.Dora{}, defaultRules(),
	)

	got := yakuSummaryOf(value)
	want := yakuHan(5, 50, play.YakuSanankou, play.YakuHonitsu)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("EstimateHandValue(444789999p22333z on 9p) = %+v, want %+v", got, want)
	}
	if wantLimit := play.Some(play.LimitMangan); value.Limit != wantLimit {
		t.Errorf("EstimateHandValue(444789999p22333z on 9p).Limit = %+v, want %+v", value.Limit, wantLimit)
	}
}

func TestEstimateHandValue_WhenTwoDragonPonsAndADragonPair_ShouldScoreShousangen(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "345m123s55666777z", winTile: "7z", situation: ron(),
		want: yakuHan(4, 50, play.YakuHatsu, play.YakuChun, play.YakuShousangen),
	})
}

func TestEstimateHandValue_WhenChiitoitsuHoldsThreeDragonPairs_ShouldNotScoreShousangen(t *testing.T) {
	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "1122m3344p556677z", winTile: "7z", situation: ron(), want: yakuHan(2, 25, play.YakuChiitoitsu),
	})
}

func TestEstimateHandValue_WhenEveryBlockHoldsATerminalOrHonor_ShouldScoreChantaiLessWhenOpen(t *testing.T) {
	hand := "123789m123s22333z"
	situation := yakuWinds(tile.North, tile.East)

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "3z", situation: situation, want: yakuHan(2, 40, play.YakuChantai)},
		yakuCase{
			hand: hand, winTile: "3z", melds: []meld.Meld{chi(t, "123s")}, situation: situation,
			want: yakuHan(1, 30, play.YakuChantai),
		},
	)
}

func TestEstimateHandValue_WhenEveryBlockHoldsATerminal_ShouldScoreJunchanLessWhenOpen(t *testing.T) {
	hand := "123789m12399p789s"

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "2m", situation: ron(), want: yakuHan(3, 40, play.YakuJunchan)},
		yakuCase{
			hand: hand, winTile: "2m", melds: []meld.Meld{chi(t, "789s")}, situation: ron(),
			want: yakuHan(2, 30, play.YakuJunchan),
		},
	)
}

func TestEstimateHandValue_WhenOneSuitWithHonors_ShouldScoreHonitsuLessWhenOpen(t *testing.T) {
	hand := "123455667m11122z"
	situation := yakuWinds(tile.West, tile.North)

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "2z", situation: situation, want: yakuHan(3, 40, play.YakuHonitsu)},
		yakuCase{
			hand: hand, winTile: "2z", melds: []meld.Meld{chi(t, "123m")}, situation: situation,
			want: yakuHan(2, 30, play.YakuHonitsu),
		},
	)
}

func TestEstimateHandValue_WhenOneSuit_ShouldScoreChinitsuLessWhenOpen(t *testing.T) {
	hand := "11234567677889m"

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "1m", situation: ron(), want: yakuHan(6, 40, play.YakuChinitsu)},
		yakuCase{
			hand: hand, winTile: "1m", melds: []meld.Meld{chi(t, "678m")}, situation: ron(),
			want: yakuHan(5, 30, play.YakuChinitsu),
		},
	)
}

func TestEstimateHandValue_WhenStraightOneToNine_ShouldScoreIttsuLessWhenOpen(t *testing.T) {
	hand := "123456789m123s22z"
	situation := yakuWinds(tile.West, tile.North)

	yakuCheckCases(t, defaultRules(),
		yakuCase{hand: hand, winTile: "3s", situation: situation, want: yakuHan(2, 40, play.YakuIttsu)},
		yakuCase{
			hand: hand, winTile: "3s", melds: []meld.Meld{chi(t, "123m")}, situation: situation,
			want: yakuHan(1, 30, play.YakuIttsu),
		},
	)
}

func TestEstimateHandValue_WhenHonorPon_ShouldScoreItsYaku(t *testing.T) {
	for _, tc := range []struct {
		name  string
		cases []yakuCase
	}{
		{"haku", []yakuCase{{
			hand: "23422m234567s555z", winTile: "5z", situation: ron(), want: yakuHan(1, 40, play.YakuHaku),
		}}},
		{"hatsu", []yakuCase{{
			hand: "23422m234567s666z", winTile: "6z", situation: ron(), want: yakuHan(1, 40, play.YakuHatsu),
		}}},
		{"chun", []yakuCase{{
			hand: "23422m234567s777z", winTile: "7z", situation: ron(), want: yakuHan(1, 40, play.YakuChun),
		}}},
		{"east as seat and round wind", yakuSeatWindCases(
			"1", tile.East, tile.West, play.YakuSeatWindEast, play.YakuRoundWindEast)},
		{"south as seat and round wind", yakuSeatWindCases(
			"2", tile.South, tile.East, play.YakuSeatWindSouth, play.YakuRoundWindSouth)},
		{"west as seat and round wind", yakuSeatWindCases(
			"3", tile.West, tile.East, play.YakuSeatWindWest, play.YakuRoundWindWest)},
		{"north as seat and round wind", yakuSeatWindCases(
			"4", tile.North, tile.East, play.YakuSeatWindNorth, play.YakuRoundWindNorth)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			yakuCheckCases(t, defaultRules(), tc.cases...)
		})
	}
}

func TestEstimateHandValue_WhenIndicatorsPointAtHandTiles_ShouldCountDoraOnlyWithAYaku(t *testing.T) {
	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: "456789m345678s55z", winTile: "5s", melds: []meld.Meld{chi(t, "678s")}, situation: ron(),
			dora: yakuIndicators(t, "5s"), wantErr: score.NoYakuError{},
		},
		yakuCase{
			hand: "123456m33p123456s", winTile: "6m", situation: ron(), dora: yakuIndicators(t, "2p"),
			want: yakuHanWithDora(3, 30, play.DoraCount{Dora: 2}, play.YakuPinfu),
		},
		yakuCase{
			hand: "22456678m123678p", winTile: "2m", situation: tsumo(), dora: yakuIndicators(t, "1m2p"),
			want: yakuHanWithDora(4, 30, play.DoraCount{Dora: 3}, play.YakuTsumo),
		},
		yakuCase{
			hand: "678m34577p123345s", winTile: "7p", situation: tsumo(), dora: yakuIndicators(t, "44s"),
			want: yakuHanWithDora(3, 30, play.DoraCount{Dora: 2}, play.YakuTsumo),
		},
		yakuCase{
			hand: "678m345p123345s66z", winTile: "5p", situation: withRiichi(ron()), dora: yakuIndicators(t, "55z"),
			want: yakuHanWithDora(5, 40, play.DoraCount{Dora: 4}, play.YakuRiichi),
		},
		yakuCase{
			hand: "123678m44p123406s", winTile: "4p", situation: tsumo(), dora: yakuIndicators(t, "22p"),
			want: yakuHanWithDora(2, 30, play.DoraCount{AkaDora: 1}, play.YakuTsumo),
		},
		yakuCase{
			hand: "7777m34577p123345s", winTile: "7p", melds: []meld.Meld{closedKan(t, "7777m")},
			situation: tsumo(), dora: yakuIndicators(t, "6m"),
			want: yakuHanWithDora(5, 40, play.DoraCount{Dora: 4}, play.YakuTsumo),
		},
	)
}

func TestEstimateHandValue_WhenUraIndicatorsPointAtHandTiles_ShouldCountUraDoraOnlyWithRiichi(t *testing.T) {
	hand := "123456m33p123456s"
	dora := score.Dora{UraIndicators: tiles(t, "2p")}

	yakuCheckCases(t, defaultRules(),
		yakuCase{
			hand: hand, winTile: "6m", situation: withRiichi(ron()), dora: dora,
			want: yakuHanWithDora(4, 30, play.DoraCount{UraDora: 2}, play.YakuRiichi, play.YakuPinfu),
		},
		yakuCase{
			hand: hand, winTile: "6m", situation: tsumo(), dora: dora,
			want: yakuHan(2, 20, play.YakuTsumo, play.YakuPinfu),
		},
	)
}

func TestEstimateHandValue_WhenHanReachesKazoe_ShouldPayASingleYakuman(t *testing.T) {
	value := yakuMustValue(
		t, "222244466677788m", "7m", []meld.Meld{closedKan(t, "2222m")}, withRiichi(ron()),
		yakuIndicators(t, "1111m"), defaultRules(),
	)

	if got, ok := value.Value.(play.Han); !ok || got.Han != 28 {
		t.Errorf("EstimateHandValue(222244466677788m on 7m).Value = %v, want 28 han", value.Value)
	}
	if want := (play.RonPayment{Discarder: 32000}); value.Payment != want {
		t.Errorf("EstimateHandValue(222244466677788m on 7m).Payment = %+v, want %+v", value.Payment, want)
	}
}

func TestEstimateHandValue_WhenDoraPassSeventyEightHan_ShouldCapHanAt78(t *testing.T) {
	dora := score.Dora{Indicators: slices.Repeat([]tile.Tile{oneTile(t, "1m")}, 20)}

	value := yakuMustValue(
		t, "222244466677788m", "7m", []meld.Meld{closedKan(t, "2222m")}, withRiichi(ron()), dora, defaultRules(),
	)

	if got, ok := value.Value.(play.Han); !ok || got.Han != 78 {
		t.Errorf("EstimateHandValue(222244466677788m on 7m).Value = %v, want 78 han", value.Value)
	}
	if want := (play.RonPayment{Discarder: 32000}); value.Payment != want {
		t.Errorf("EstimateHandValue(222244466677788m on 7m).Payment = %+v, want %+v", value.Payment, want)
	}
	if want := play.Some(play.LimitYakuman); value.Limit != want {
		t.Errorf("EstimateHandValue(222244466677788m on 7m).Limit = %+v, want %+v", value.Limit, want)
	}
}

func TestEstimateHandValue_WhenOpenRonHasNoFuAndOpenPinfuTakesNone_ShouldScore20Fu(t *testing.T) {
	rules := defaultRules()
	rules.OpenTanyao = true
	rules.FuForOpenPinfu = false

	value := yakuMustValue(t, "234567m22p234678s", "6s", []meld.Meld{chi(t, "234s")}, ron(), score.Dora{}, rules)

	got := yakuSummaryOf(value)
	want := yakuHan(1, 20, play.YakuTanyao)
	if !reflect.DeepEqual(got, want) {
		t.Errorf("EstimateHandValue(234567m22p234678s on 6s) = %+v, want %+v", got, want)
	}
	if wantPayment := (play.RonPayment{Discarder: 700}); value.Payment != wantPayment {
		t.Errorf("EstimateHandValue(234567m22p234678s on 6s).Payment = %+v, want %+v", value.Payment, wantPayment)
	}
}

func TestEstimateHandValue_WhenOpenTsumoHasNoOtherFu_ShouldScore30FuWhateverTheOpenPinfuRule(t *testing.T) {
	want := yakuHan(1, 30, play.YakuTanyao)
	wantFu := []score.FuDetail{{Fu: 20, Reason: score.FuBase}, {Fu: 2, Reason: score.FuTsumo}}
	wantPayment := play.TsumoPayment{Dealer: 500, NonDealer: 300}

	for _, fuForOpenPinfu := range []bool{true, false} {
		t.Run(fmt.Sprintf("FuForOpenPinfu=%t", fuForOpenPinfu), func(t *testing.T) {
			rules := defaultRules()
			rules.OpenTanyao = true
			rules.FuForOpenPinfu = fuForOpenPinfu

			value := yakuMustValue(
				t, "234567m22p234678s", "6s", []meld.Meld{chi(t, "234s")}, tsumo(), score.Dora{}, rules,
			)

			if got := yakuSummaryOf(value); !reflect.DeepEqual(got, want) {
				t.Errorf("EstimateHandValue(FuForOpenPinfu=%v) = %+v, want %+v", fuForOpenPinfu, got, want)
			}
			if !reflect.DeepEqual(value.FuDetails, wantFu) {
				t.Errorf("EstimateHandValue(FuForOpenPinfu=%v).FuDetails = %+v, want %+v",
					fuForOpenPinfu, value.FuDetails, wantFu)
			}
			if value.Payment != wantPayment {
				t.Errorf("EstimateHandValue(FuForOpenPinfu=%v).Payment = %+v, want %+v",
					fuForOpenPinfu, value.Payment, wantPayment)
			}
		})
	}
}

func TestEstimateHandValue_WhenHandHoldsRedFives_ShouldCountEachAsAkaDora(t *testing.T) {
	cases := []struct {
		hand string
		han  int
	}{
		{"12305599m406p340s", 4},
		{"12355599m456p345s", 1},
		{"12355599m456p34rs", 2},
		{"12355599m4r6p34rs", 3},
		{"123r5599m4r6p34rs", 4},
		{"123rr599m4r6p34rs", 5},
		{"123rrr99m4r6p34rs", 6},
	}

	for _, c := range cases {
		t.Run(c.hand, func(t *testing.T) {
			yakuCheckCases(t, defaultRules(), yakuCase{
				hand: c.hand, winTile: "9m", situation: tsumo(),
				want: yakuHanWithDora(c.han, 30, play.DoraCount{AkaDora: c.han - 1}, play.YakuTsumo),
			})
		})
	}
}

func TestEstimateHandValue_WhenDoraIsAHonorTheHandLacks_ShouldCountNoDora(t *testing.T) {
	for _, indicators := range []string{"", "3z", "33z"} {
		t.Run(fmt.Sprintf("indicators %q", indicators), func(t *testing.T) {
			yakuCheckCases(t, defaultRules(), yakuCase{
				hand: "12355599m456p345s", winTile: "9m", situation: tsumo(), dora: yakuIndicators(t, indicators),
				want: yakuHan(1, 30, play.YakuTsumo),
			})
		})
	}
}

func TestEstimateHandValue_WhenUraDoraIsAHonorTheHandLacks_ShouldCountNoUraDora(t *testing.T) {
	for _, uraIndicators := range []string{"", "3z", "33z"} {
		t.Run(fmt.Sprintf("ura indicators %q", uraIndicators), func(t *testing.T) {
			yakuCheckCases(t, defaultRules(), yakuCase{
				hand: "12355599m456p345s", winTile: "9m", situation: withRiichi(ron()),
				dora: score.Dora{UraIndicators: tiles(t, uraIndicators)},
				want: yakuHan(1, 40, play.YakuRiichi),
			})
		})
	}
}

func TestEstimateHandValue_WhenIndicatorIsOneMan_ShouldMakeTwoManDoraNotNineMan(t *testing.T) {
	situation := withRiichi(yakuWinds(tile.West, tile.North))

	yakuCheckCases(t, defaultRules(), yakuCase{
		hand: "99m456789p345s111z", winTile: "9m", situation: situation,
		dora: score.Dora{Indicators: tiles(t, "1m"), UraIndicators: tiles(t, "11m")},
		want: yakuHan(1, 40, play.YakuRiichi),
	})
}
