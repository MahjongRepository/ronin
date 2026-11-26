package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func souWithHighPin(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789s6789p")
}

func dealerIttsuTankiOnFivePin(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "123456789m1235p")
}

func fivePinWinTile(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 1, "5p")
}

func twoManDoraIndicator(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 1, "1m")
}

func eastDoraIndicator(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 0, "4z")
}

func soleRon(t *testing.T, events []play.Emitted) play.Ron {
	t.Helper()
	ron := ronResult(t, events)
	assertEqual(t, "head bumped", ron.HeadBumped, []tile.Seat(nil))
	return ron
}

func ittsuDealerHands(t *testing.T) [tile.SeatCount][]tile.TileID {
	t.Helper()
	return [tile.SeatCount][]tile.TileID{
		dealerIttsuTankiOnFivePin(t), souWithHighPin(t, 1), souWithHighPin(t, 2), souWithHighPin(t, 3),
	}
}

func dealerRiichiOnSecondDiscard(t *testing.T, afterTwoMoreGoArounds []tile.TileID) game.Game {
	t.Helper()
	draws := slices.Concat(copies(t, 0, "1111z"), copies(t, 0, "2222z"), afterTwoMoreGoArounds)
	g := goAroundGame(t, ittsuDealerHands(t), draws, eastStart(sticksPaidScores(1), 1, 1), twoManDoraIndicator(t))
	g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(tileOf(t, 0, "1z"))))
	g, _ = discardDrawn(t, g, 7)
	return g
}

func TestTsumo_WhenAClosedTankiWins_ShouldReturnTheScoredResult(t *testing.T) {
	g := goAroundGame(t, ittsuDealerHands(t), []tile.TileID{fivePinWinTile(t)}, noStart(), twoManDoraIndicator(t))

	win := winOf(t, g, seat(t, 0), play.TsumoAction())
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuIttsu})
	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 1, AkaDora: 2})
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 6, Fu: 30})
	assertEqual(t, "limit", win.Limit, play.Some(play.LimitHaneman))
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{18000, -6000, -6000, -6000})
	assertEqual(t, "ura indicators", win.UraIndicators, []tile.TileID(nil))
}

func TestTsumo_WhenTheWinnerIsInRiichi_ShouldIncludeTheRiichiYaku(t *testing.T) {
	g := dealerRiichiOnSecondDiscard(t, []tile.TileID{fivePinWinTile(t)})

	win := winOf(t, g, seat(t, 0), play.TsumoAction())
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuRiichi, play.YakuIttsu})
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 7, Fu: 30})
}

func TestTsumo_WhenARiichiDealerWinsWithHonbaAndSticks_ShouldChargeEachSeatEquallyAndClearTheSticks(t *testing.T) {
	g := dealerRiichiOnSecondDiscard(t, []tile.TileID{fivePinWinTile(t)})
	assertEqual(t, "scores before", g.Scores(), [tile.SeatCount]int{23000, 25000, 25000, 25000})

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	tsumo, ok := roundResult(t, events).(play.Tsumo)
	if !ok {
		t.Fatalf("result = %+v, want a tsumo", roundResult(t, events))
	}
	assertEqual(t, "limit", tsumo.Win.Limit, play.Some(play.LimitHaneman))
	assertEqual(t, "score changes", tsumo.Win.ScoreChanges, [tile.SeatCount]int{20300, -6100, -6100, -6100})
	assertEqual(t, "hand", tsumo.Win.Hand, dealerIttsuTankiOnFivePin(t))
	assertEqual(t, "win tile", tsumo.Win.WinTile, fivePinWinTile(t))
	assertEqual(t, "ura indicators", tsumo.Win.UraIndicators, []tile.TileID{doraFreeUra(t)})
	ended, ok := events[len(events)-1].Event.(play.RoundEnded)
	if !ok {
		t.Fatalf("last event = %+v, want the round's end", events[len(events)-1].Event)
	}
	assertEqual(t, "scores", ended.Scores, [tile.SeatCount]int{43300, 18900, 18900, 18900})
	assertEqual(t, "riichi sticks", ended.RiichiSticks, 0)
}

func TestRon_WhenTheWinnerIsInRiichi_ShouldNotIncludeMenzenTsumo(t *testing.T) {
	g := dealerRiichiOnSecondDiscard(t, []tile.TileID{tileOf(t, 0, "3z"), tileOf(t, 1, "3z"), tileOf(t, 2, "3z"), tileOf(t, 2, "5p")})
	g, _ = discardDrawn(t, g, tile.SeatCount)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))

	_, events := script(t, g, act(seat(t, 0), play.RonAction()))

	ron := soleRon(t, events)
	assertEqual(t, "discarder", ron.Discarder, seat(t, 3))
	assertEqual(t, "yaku", ron.Wins[0].Yaku, []play.YakuID{play.YakuRiichi, play.YakuIttsu})
	assertEqual[play.Value](t, "value", ron.Wins[0].Value, play.Han{Han: 6, Fu: 40})
}

func TestTsumo_WhenANonDealerWinsWithHonba_ShouldRoundThePaymentsUpAndAddTheHonbaPerLoser(t *testing.T) {
	hands := [tile.SeatCount][]tile.TileID{
		souWithHighPin(t, 0),
		slices.Concat(copies(t, 0, "12346789m123p"), copies(t, 1, "5m5p")),
		souWithHighPin(t, 2),
		souWithHighPin(t, 3),
	}
	draws := []tile.TileID{tileOf(t, 0, "1z"), tileOf(t, 2, "5p")}
	g := goAroundGame(t, hands, draws, eastStart([tile.SeatCount]int{25000, 25000, 25000, 25000}, 1, 0), eastDoraIndicator(t))
	g, _ = discardDrawn(t, g, 1)

	win := winOf(t, g, seat(t, 1), play.TsumoAction())
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuIttsu})
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 3, Fu: 30})
	assertEqual(t, "limit", win.Limit, play.Option[play.Limit]{})
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{-2100, 4300, -1100, -1100})
}

func threePinDiscardedBy(t *testing.T, loser tile.Seat) game.Game {
	t.Helper()
	manWithHonors := func(first int) []tile.TileID { return copies(t, first, "123456789m4567z") }
	var hands [tile.SeatCount][]tile.TileID
	hands[0] = slices.Concat(copies(t, 0, "123456789s"), copies(t, 1, "12p"), copies(t, 2, "5p"), copies(t, 3, "5p"))
	hands[2] = copies(t, 0, "123456789m1255p")
	seats := tile.Seats()
	for _, other := range seats[1:] {
		switch {
		case other == loser:
			hands[other.Index()] = manWithHonors(1)
		case other != seat(t, 2):
			hands[other.Index()] = manWithHonors(2)
		}
	}

	threePin := tileOf(t, 0, "3p")
	w := testkit.StartWall{
		Hands: hands,
		Draws: slices.Concat(
			copies(t, 0, "123z"), copies(t, 1, "123z"), copies(t, 2, "123z"), copies(t, 3, "123z"),
			copies(t, 0, "888p")[:loser.Index()], []tile.TileID{threePin},
		),
		Dora: play.Some(eastDoraIndicator(t)),
		Ura:  []tile.TileID{doraFreeUra(t)},
	}
	g, _ := discardDrawn(t, begun(t, w, eastStart(sticksPaidScores(1), 2, 1)), 6)
	g, _ = script(t, g, act(seat(t, 2), play.RiichiAction(tileOf(t, 2, "1z"))))
	g, _ = discardDrawn(t, g, 5+loser.Index()+1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0), seat(t, 2)))
	return g
}

func assertSticksCleared(t *testing.T, events []play.Emitted) {
	t.Helper()
	ended, ok := events[len(events)-1].Event.(play.RoundEnded)
	if !ok {
		t.Fatalf("last event = %+v, want the round's end", events[len(events)-1].Event)
	}
	assertEqual(t, "riichi sticks", ended.RiichiSticks, 0)
}

func TestRon_WhenHonbaAndRiichiSticksAreOnTheTable_ShouldChargeTheDiscarderAndGiveTheSticksToTheWinner(t *testing.T) {
	g := threePinDiscardedBy(t, seat(t, 1))

	_, events := script(t, g, act(seat(t, 0), play.PassAction()), act(seat(t, 2), play.RonAction()))

	ron := soleRon(t, events)
	assertEqual(t, "discarder", ron.Discarder, seat(t, 1))
	if len(ron.Wins) != 1 {
		t.Fatalf("wins = %+v, want one", ron.Wins)
	}

	win := ron.Wins[0]
	assertEqual(t, "winner", win.Winner, seat(t, 2))
	assertEqual(t, "loser", win.Loser, play.Some(seat(t, 1)))
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 5, Fu: 40})
	assertEqual(t, "limit", win.Limit, play.Some(play.LimitMangan))
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{0, -8600, 10600, 0})
	assertEqual(t, "ura indicators", win.UraIndicators, []tile.TileID{doraFreeUra(t)})
	assertSticksCleared(t, events)
}

func TestDoubleRon_ShouldChargeTheDiscarderBothHandsAndGiveHonbaAndSticksToTheCloserWinner(t *testing.T) {
	for _, c := range []struct {
		name                   string
		loser, closer, farther tile.Seat
		scoreChanges           [tile.SeatCount]int
	}{
		{
			name:         "seat 1 discards",
			loser:        seat(t, 1),
			closer:       seat(t, 2),
			farther:      seat(t, 0),
			scoreChanges: [tile.SeatCount]int{7700, -16300, 10600, 0},
		},
		{
			name:         "seat 3 discards",
			loser:        seat(t, 3),
			closer:       seat(t, 0),
			farther:      seat(t, 2),
			scoreChanges: [tile.SeatCount]int{10300, 0, 8000, -16300},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			g := threePinDiscardedBy(t, c.loser)

			_, events := script(t, g, act(seat(t, 0), play.RonAction()), act(seat(t, 2), play.RonAction()))

			ron := soleRon(t, events)
			assertEqual(t, "winners", winners(ron), []tile.Seat{c.closer, c.farther})
			for _, win := range ron.Wins {
				want := []tile.TileID(nil)
				if win.Winner == seat(t, 2) {
					want = []tile.TileID{doraFreeUra(t)}
				}
				assertEqual(t, "ura indicators", win.UraIndicators, want)
			}
			assertEqual(t, "score changes", ron.TotalScoreChanges(), c.scoreChanges)
			assertSticksCleared(t, events)
		})
	}
}

func pinWithHighTerminals(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789p9m9s56z")
}

func dealerTsumoFu(t *testing.T, hand []tile.TileID, winTile tile.TileID, wind tile.Wind, bystander func(int) []tile.TileID) play.WinResult {
	t.Helper()
	hands := [tile.SeatCount][]tile.TileID{hand, bystander(1), bystander(2), bystander(3)}
	start := testkit.EastStart([tile.SeatCount]int{25000, 25000, 25000, 25000}, 0, 0)
	start.Wind = wind
	g := goAroundGame(t, hands, []tile.TileID{winTile}, play.Some(start), tileOf(t, 0, "9m"))
	return winOf(t, g, seat(t, 0), play.TsumoAction())
}

func fuOf(t *testing.T, value play.Value) int {
	t.Helper()
	han, ok := value.(play.Han)
	if !ok {
		t.Fatalf("value = %v, want han and fu", value)
	}

	return han.Fu
}

func souWithHighPinOf(t *testing.T) func(int) []tile.TileID {
	t.Helper()
	return func(first int) []tile.TileID { return souWithHighPin(t, first) }
}

func TestFu_WhenThePairIsADoubleWind_ShouldAdd4(t *testing.T) {
	win := dealerTsumoFu(t, copies(t, 0, "123456m789p23s11z"), tileOf(t, 0, "4s"), tile.East, souWithHighPinOf(t))
	assertEqual(t, "fu", fuOf(t, win.Value), 30)
}

func TestFu_WhenThePairIsASingleWind_ShouldAdd2(t *testing.T) {
	win := dealerTsumoFu(t, copies(t, 0, "123456m789p23s11z"), tileOf(t, 0, "4s"), tile.South, souWithHighPinOf(t))
	assertEqual(t, "fu", fuOf(t, win.Value), 30)
}

func riichiRonFuWithAnEastPair(t *testing.T, wind tile.Wind) int {
	t.Helper()
	hand := slices.Concat(copies(t, 0, "111m4m"), copies(t, 1, "5m"), copies(t, 0, "6m789p23s11z"))
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			hand, pinWithHighTerminals(t, 1), pinWithHighTerminals(t, 2), pinWithHighTerminals(t, 3),
		},
		Draws: []tile.TileID{tileOf(t, 0, "7z"), tileOf(t, 0, "4s")},
		Dora:  play.Some(tileOf(t, 0, "9s")),
		Ura:   []tile.TileID{doraFreeUra(t)},
	}
	start := testkit.EastStart([tile.SeatCount]int{25000, 25000, 25000, 25000}, 0, 0)
	start.Wind = wind
	g, _ := script(t, begun(t, w, play.Some(start)), act(seat(t, 0), play.RiichiAction(tileOf(t, 0, "7z"))))
	g, _ = discardDrawn(t, g, 1)
	_, events := script(t, g, act(seat(t, 0), play.RonAction()))
	return fuOf(t, soleRon(t, events).Wins[0].Value)
}

func TestRonFu_WhenThePairIsADoubleRatherThanASingleWind_ShouldBeHigher(t *testing.T) {
	assertEqual(t, "double wind fu", riichiRonFuWithAnEastPair(t, tile.East), 50)
	assertEqual(t, "single wind fu", riichiRonFuWithAnEastPair(t, tile.South), 40)
}

func TestPinfuTsumo_WhenThePairIsUnvalued_ShouldScore20FuWithoutTsumoFu(t *testing.T) {
	hands := [tile.SeatCount][]tile.TileID{
		pinWithHighTerminals(t, 1), copies(t, 0, "123456m789p2355s"), pinWithHighTerminals(t, 2), pinWithHighTerminals(t, 3),
	}
	g := goAroundGame(t, hands, []tile.TileID{tileOf(t, 0, "1z"), tileOf(t, 0, "4s")}, noStart(), tileOf(t, 0, "9m"))
	g, _ = discardDrawn(t, g, 1)

	win := winOf(t, g, seat(t, 1), play.TsumoAction())
	if !hasYaku(win.Yaku, play.YakuPinfu) {
		t.Errorf("yaku = %v, want pinfu", win.Yaku)
	}
	assertEqual(t, "fu", fuOf(t, win.Value), 20)
}

func TestChiitoitsu_ShouldScore25FuAndItsYaku(t *testing.T) {
	bystander := func(first int) []tile.TileID { return copies(t, first, "456789m34568p49s") }

	win := dealerTsumoFu(t, copies(t, 0, "1133m2277p5588s1z"), tileOf(t, 1, "1z"), tile.East, bystander)
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuChiitoitsu})
	if han, ok := win.Value.(play.Han); !ok || han.Fu != 25 || han.Han < 3 {
		t.Errorf("value = %v, want 3 han or more at 25 fu", win.Value)
	}
}

func TestRon_WhenTheHandIs4HanAnd40Fu_ShouldReportTheManganLimit(t *testing.T) {
	bystander := func(first int) []tile.TileID { return copies(t, first, "123456789p159s1z") }
	winner := slices.Concat(copies(t, 0, "123m"), copies(t, 1, "5m"), copies(t, 0, "6778m22555z"))
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{bystander(0), winner, bystander(1), bystander(2)},
		Draws: []tile.TileID{tileOf(t, 0, "9m")},
		Dora:  play.Some(tileOf(t, 3, "9p")),
		Ura:   []tile.TileID{doraFreeUra(t)},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)

	_, events := script(t, g, act(seat(t, 1), play.RonAction()))

	win := soleRon(t, events).Wins[0]
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 4, Fu: 40})
	assertEqual(t, "limit", win.Limit, play.Some(play.LimitMangan))
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{-8000, 8000, 0, 0})
}

func TestRon_WhenTheHandIs4HanAnd30Fu_ShouldScore7700(t *testing.T) {
	bystander := func(first int) []tile.TileID { return copies(t, first, "6789m189p156789s") }
	winner := slices.Concat(copies(t, 0, "223344m"), copies(t, 1, "5m567p"), copies(t, 0, "234s"))
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{bystander(0), winner, bystander(1), bystander(2)},
		Draws: slices.Concat(copies(t, 0, "1234z"), copies(t, 1, "1234z"), copies(t, 2, "12z"), copies(t, 2, "5m")),
		Dora:  play.Some(tileOf(t, 3, "9p")),
		Ura:   []tile.TileID{doraFreeUra(t)},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 5)
	g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(tileOf(t, 1, "2z"))))
	g, _ = discardDrawn(t, g, 5)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 3)))

	_, events := script(t, g, act(seat(t, 3), play.PassAction()), act(seat(t, 1), play.RonAction()))

	win := soleRon(t, events).Wins[0]
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuRiichi, play.YakuPinfu, play.YakuTanyao, play.YakuIipeikou})
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 4, Fu: 30})
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{0, 8700, -7700, 0})
}

func TestRon_WhenTheHandIsOpen_ShouldScoreItsYakuhaiMeld(t *testing.T) {
	extra := tileOf(t, 0, "7z")
	dealer := slices.Concat(copies(t, 1, "55z"), copies(t, 0, "234567m2355s"), []tile.TileID{extra})
	laterDraws := slices.Concat(copies(t, 0, "66z"), copies(t, 0, "4s"))
	g := dealerPonFromSeatThree(t, dealer, tileOf(t, 0, "5z"), extra, laterDraws, play.Some(twoManDoraIndicator(t)))
	g, _ = discardDrawn(t, g, 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))
	if !containsAction(g.LegalActions(seat(t, 0)), play.RonAction()) {
		t.Fatal("ron is not offered")
	}

	_, events := script(t, g, act(seat(t, 0), play.RonAction()))

	win := soleRon(t, events).Wins[0]
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuHaku})
	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 1, AkaDora: 2})
	assertEqual[play.Value](t, "value", win.Value, play.Han{Han: 4, Fu: 30})
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{11600, 0, 0, -11600})
}

func TestTsumo_WhenAnOpenHandHasNoYaku_ShouldNotBeOffered(t *testing.T) {
	extra := tileOf(t, 0, "6z")
	dealer := slices.Concat(copies(t, 1, "11m"), copies(t, 0, "34m234p567s77z"), []tile.TileID{extra})
	laterDraws := slices.Concat(copies(t, 1, "666z"), copies(t, 1, "5m"))
	g := dealerPonFromSeatThree(t, dealer, tileOf(t, 0, "1m"), extra, laterDraws, play.Some(tileOf(t, 3, "9m")))
	g, _ = discardDrawn(t, g, 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))

	if containsAction(g.LegalActions(seat(t, 0)), play.TsumoAction()) {
		t.Error("tsumo is offered to an open hand without yaku")
	}
}

func TestRon_WhenAnOpenPinfuShapeWins_ShouldScore30Fu(t *testing.T) {
	extra, calledTwoMan := tileOf(t, 0, "7z"), tileOf(t, 0, "2m")
	threeFourMan := [2]tile.TileID{tileOf(t, 0, "3m"), tileOf(t, 0, "4m")}
	dealer := slices.Concat(threeFourMan[:], copies(t, 0, "567m234p23s"), copies(t, 1, "55m"), []tile.TileID{extra})
	laterDraws := slices.Concat(copies(t, 0, "66z"), copies(t, 0, "4s"))
	g, err := testkit.DealerCallFromSeatThree(dealer, calledTwoMan, play.ChiAction(threeFourMan), extra, laterDraws,
		play.Some(tileOf(t, 3, "9m")))
	if err != nil {
		t.Fatalf("DealerCallFromSeatThree error = %v", err)
	}

	g, _ = discardDrawn(t, g, 3)

	_, events := script(t, g, act(seat(t, 0), play.RonAction()))

	win := soleRon(t, events).Wins[0]
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTanyao, play.YakuSanshoku})
	assertEqual(t, "fu", fuOf(t, win.Value), 30)
}
