package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func dealerAfterDrawFrom(t *testing.T, dealer, draws []tile.TileID, start play.Option[play.StartPosition]) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{dealer, souWithWinds(t, 1), souWithWinds(t, 2), souWithWinds(t, 3)},
		Draws: draws,
	}
	return begun(t, w, start)
}

func dealerAfterDraw(t *testing.T, dealer, draws []tile.TileID) game.Game {
	t.Helper()
	return dealerAfterDrawFrom(t, dealer, draws, noStart())
}

func tenpaiOnOneAndNineMan(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "1123456788899m")
}

func drawnChun(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 0, "7z")
}

func tenpaiDealerAfterDraw(t *testing.T) game.Game {
	t.Helper()
	return dealerAfterDraw(t, tenpaiOnOneAndNineMan(t), []tile.TileID{drawnChun(t)})
}

func riichis(g game.Game) []play.Action {
	var offered []play.Action
	for _, action := range g.LegalActions(tile.Seats()[0]) {
		if action.Kind() == play.ActionRiichi {
			offered = append(offered, action)
		}
	}
	return offered
}

func riichiActions(held []tile.TileID) []play.Action {
	actions := make([]play.Action, len(held))
	for i, h := range held {
		actions[i] = play.RiichiAction(h)
	}
	return actions
}

func pinWithWinds(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789p1234z")
}

func hasYaku(yaku []play.YakuID, id play.YakuID) bool {
	return slices.Contains(yaku, id)
}

func TestLegalActions_WhenAClosedHandCanRiichi_ShouldListEveryDiscardThenOnlyTheTenpaiKeepingRiichis(t *testing.T) {
	pinOnes, stray := copies(t, 0, "11p"), tileOf(t, 0, "9s")
	dealt := slices.Concat(copies(t, 0, "123456789m"), pinOnes, copies(t, 0, "23p"))
	g := dealerAfterDraw(t, dealt, []tile.TileID{stray})

	want := slices.Concat(discards(slices.Concat(dealt, []tile.TileID{stray})),
		riichiActions(slices.Concat(pinOnes, []tile.TileID{stray})))
	assertEqual(t, "legal actions", g.LegalActions(seat(t, 0)), want)
}

func TestRiichi_WhenTheScoreIsBelowOrAtOneThousand_ShouldBeOfferedOnlyFromOneThousand(t *testing.T) {
	for _, score := range []int{900, 1000} {
		start := play.Some(testkit.EastStart([tile.SeatCount]int{score, 25000, 25000, 50000 - score}, 0, 0))
		g := dealerAfterDrawFrom(t, tenpaiOnOneAndNineMan(t), []tile.TileID{drawnChun(t)}, start)

		if offered := len(riichis(g)) > 0; offered != (score >= 1000) {
			t.Errorf("score %d: riichi offered = %t", score, offered)
		}
	}
}

func TestRiichi_WhenTheHandIsNotTenpai_ShouldBeNeitherOfferedNorAccepted(t *testing.T) {
	g := dealerAfterDraw(t, copies(t, 0, "13579m2468p1357s"), []tile.TileID{drawnChun(t)})

	assertEqual(t, "riichis", riichis(g), []play.Action(nil))
	assertRefused(t, g, seat(t, 0), play.RiichiAction(drawnChun(t)), notOfferedRefusal())
}

func TestRiichi_WhenTheDrawnHandIsComplete_ShouldBeOfferedOnEveryTile(t *testing.T) {
	g := dealerAfterDraw(t, tenpaiOnOneAndNineMan(t), []tile.TileID{tileOf(t, 3, "9m")})

	assertEqual(t, "riichis", riichis(g), riichiActions(g.Hand(seat(t, 0))))
}

func TestRiichi_WhenTheSeatIsInDiscardFuriten_ShouldStillBeOffered(t *testing.T) {
	draws := slices.Concat(copies(t, 2, "1m"), copies(t, 0, "567z"), copies(t, 1, "7z"))
	g, goneAround := discardDrawn(t, dealerAfterDraw(t, tenpaiOnOneAndNineMan(t), draws), 4)
	assertEqual(t, "furiten", testkit.FuritenChanges(goneAround), []play.FuritenChanged{{Seat: seat(t, 0), Furiten: true}})

	if len(riichis(g)) == 0 {
		t.Error("riichi is not offered in discard furiten")
	}
}

func TestRiichi_WhenTheSeatIsInTemporaryFuriten_ShouldStillBeOffered(t *testing.T) {
	draws := slices.Concat(copies(t, 1, "7z"), copies(t, 2, "1m"), copies(t, 0, "56z"), []tile.TileID{drawnChun(t)})
	g, _ := discardDrawn(t, dealerAfterDraw(t, tenpaiOnOneAndNineMan(t), draws), 2)
	g, passed := script(t, g, act(seat(t, 0), play.PassAction()))
	assertEqual(t, "furiten", testkit.FuritenChanges(passed), []play.FuritenChanged{{Seat: seat(t, 0), Furiten: true}})
	g, _ = discardDrawn(t, g, 2)

	if len(riichis(g)) == 0 {
		t.Error("riichi is not offered in temporary furiten")
	}
}

func TestRiichi_WhenValid_ShouldEmitTheRiichiDiscardThenDepositTheStick(t *testing.T) {
	g := tenpaiDealerAfterDraw(t)
	if !containsAction(riichis(g), play.RiichiAction(drawnChun(t))) {
		t.Fatal("riichi on the drawn tile is not offered")
	}

	g, events := script(t, g, act(seat(t, 0), play.RiichiAction(drawnChun(t))))

	assertEqual(t, "first events", events[:2], []play.Emitted{
		{To: play.ToAll(), Event: play.Discarded{Seat: seat(t, 0), Tile: drawnChun(t), Tsumogiri: true, Riichi: true}},
		{To: play.ToAll(), Event: play.RiichiDeposited{Seat: seat(t, 0), Score: 24000, RiichiSticks: 1}},
	})
	assertEqual(t, "scores", g.Scores(), [tile.SeatCount]int{24000, 25000, 25000, 25000})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
}

func TestRiichi_WhenItIsNotTheSeatsTurn_ShouldBeNotAwaited(t *testing.T) {
	g := tenpaiDealerAfterDraw(t)

	assertRefused(t, g, seat(t, 1), play.RiichiAction(g.Hand(seat(t, 1))[0]), seatNotAwaitedRefusal())
}

func TestRiichiDiscard_WhenTheDiscardBreaksTenpai_ShouldBeRefusedByRuleAndChangeNothing(t *testing.T) {
	assertRefused(t, tenpaiDealerAfterDraw(t), seat(t, 0), play.RiichiAction(tileOf(t, 0, "3m")),
		refusal(play.RefusalRule, play.CodeRiichiBreaksTenpai))
}

func TestRiichi_WhenTheHandIsTenpaiAndTheTileIsNotHeld_ShouldBeNotOffered(t *testing.T) {
	g := tenpaiDealerAfterDraw(t)

	assertRefused(t, g, seat(t, 0), play.RiichiAction(g.Hand(seat(t, 1))[0]),
		refusal(play.RefusalNotOffered, play.CodeTileNotHeld))
}

func riichiDealerAfterItsNextDraw(t *testing.T) game.Game {
	t.Helper()
	draws := slices.Concat([]tile.TileID{drawnChun(t)}, copies(t, 0, "56z"), copies(t, 1, "7z"), copies(t, 1, "5z"))
	g, _ := script(t, dealerAfterDraw(t, tenpaiOnOneAndNineMan(t), draws), act(seat(t, 0), play.RiichiAction(drawnChun(t))))
	g, _ = discardDrawn(t, g, 3)
	return g
}

func TestLegalActions_WhenTheSeatIsInRiichi_ShouldOfferOnlyTheDrawnTileAndNoSecondRiichi(t *testing.T) {
	g := riichiDealerAfterItsNextDraw(t)

	assertEqual(t, "legal actions", g.LegalActions(seat(t, 0)), discards(copies(t, 1, "5z")))
}

func TestDiscard_WhenRiichiForbidsTheTile_ShouldBeRefusedByRuleAndChangeNothing(t *testing.T) {
	g := riichiDealerAfterItsNextDraw(t)

	assertRefused(t, g, seat(t, 0), play.DiscardAction(g.Hand(seat(t, 0))[0]),
		refusal(play.RefusalRule, play.CodeRiichiDrawnTileOnly))
}

func riichiRonYakuWithinIppatsu(t *testing.T, earlierGoArounds int) []play.YakuID {
	t.Helper()
	riichiDiscard, oneMan := tileOf(t, 1, "7z"), tileOf(t, 2, "1m")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			tenpaiOnOneAndNineMan(t),
			copies(t, 1, "123456789p159s5z"),
			copies(t, 2, "123456789p159s5z"),
			copies(t, 3, "123456789p159s5z"),
		},
		Draws: slices.Concat(copies(t, 0, "1234z")[:tile.SeatCount*earlierGoArounds], []tile.TileID{riichiDiscard, oneMan}),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), tile.SeatCount*earlierGoArounds)
	g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(riichiDiscard)))
	g, _ = discardDrawn(t, g, 1)

	_, events := script(t, g, act(seat(t, 0), play.RonAction()))
	return firstWin(t, events).Yaku
}

func TestRiichi_WhenTheRiichiDiscardIsTheFirstDiscard_ShouldScoreDaburuRiichiAndIppatsu(t *testing.T) {
	yaku := riichiRonYakuWithinIppatsu(t, 0)

	if !hasYaku(yaku, play.YakuDaburuRiichi) || !hasYaku(yaku, play.YakuIppatsu) {
		t.Errorf("yaku = %v, want daburu riichi and ippatsu", yaku)
	}
}

func TestRiichi_WhenTheSeatHasAlreadyDiscarded_ShouldScoreRiichiAndIppatsuButNotDaburuRiichi(t *testing.T) {
	yaku := riichiRonYakuWithinIppatsu(t, 1)

	if !hasYaku(yaku, play.YakuRiichi) || !hasYaku(yaku, play.YakuIppatsu) || hasYaku(yaku, play.YakuDaburuRiichi) {
		t.Errorf("yaku = %v, want riichi and ippatsu without daburu riichi", yaku)
	}
}

func TestRiichiDiscard_WhenItIsRonned_ShouldNeverDepositItsStick(t *testing.T) {
	threePin := tileOf(t, 0, "3p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			tenpaiOnOneAndNineMan(t), copies(t, 1, "123456789s1255p"), souWithWinds(t, 2), souWithWinds(t, 3),
		},
		Draws: []tile.TileID{threePin},
	}
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), play.RiichiAction(threePin)))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))

	_, events := script(t, g, act(seat(t, 1), play.RonAction()))

	if slices.Contains(testkit.EventKinds(events), "riichi_deposited") {
		t.Error("the ronned riichi discard deposited its stick")
	}
	ended, ok := events[len(events)-1].Event.(play.RoundEnded)
	if !ok {
		t.Fatalf("last event = %+v, want the round's end", events[len(events)-1].Event)
	}
	assertEqual(t, "scores", ended.Scores, [tile.SeatCount]int{22400, 27600, 25000, 25000})
	assertEqual(t, "riichi sticks", ended.RiichiSticks, 0)
}

func TestRiichi_WhenTheHandHasAnOpenMeld_ShouldBeNeitherOfferedNorAccepted(t *testing.T) {
	drawnEast, extraChun := tileOf(t, 1, "1z"), tileOf(t, 0, "7z")
	dealer := slices.Concat(copies(t, 1, "11m"), copies(t, 1, "2345678889m"), []tile.TileID{extraChun})
	g := dealerPonFromSeatThree(t, dealer, tileOf(t, 0, "1m"), extraChun,
		slices.Concat(copies(t, 0, "666z"), []tile.TileID{drawnEast}), play.Option[tile.TileID]{})
	g, _ = discardDrawn(t, g, 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))

	assertEqual(t, "riichis", riichis(g), []play.Action(nil))
	assertRefused(t, g, seat(t, 0), play.RiichiAction(drawnEast), notOfferedRefusal())
}

func TestRiichi_WhenTheFirstDiscardFollowsACall_ShouldScoreRiichiAndIppatsuButNotDaburuRiichi(t *testing.T) {
	south, east := copies(t, 0, "2222z"), copies(t, 0, "1111z")
	riichiDiscard := tileOf(t, 0, "7z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789p1234s"),
			tenpaiOnOneAndNineMan(t),
			slices.Concat(copies(t, 1, "123456789p1s"), south[1:3], east[2:3]),
			copies(t, 2, "123456789p1234s"),
		},
		Draws: []tile.TileID{south[0], east[3], east[0], riichiDiscard, tileOf(t, 2, "1m")},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	g, _ = script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))), act(seat(t, 2), play.DiscardAction(east[2])))
	g, _ = discardDrawn(t, g, 2)
	g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(riichiDiscard)))
	g, _ = discardDrawn(t, g, 1)

	_, events := script(t, g, act(seat(t, 1), play.RonAction()))

	yaku := firstWin(t, events).Yaku
	if !hasYaku(yaku, play.YakuRiichi) || !hasYaku(yaku, play.YakuIppatsu) || hasYaku(yaku, play.YakuDaburuRiichi) {
		t.Errorf("yaku = %v, want riichi and ippatsu without daburu riichi", yaku)
	}
}

func dealerAfterClosedKan(t *testing.T, dealer []tile.TileID, draw, kanTile tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands:   [tile.SeatCount][]tile.TileID{dealer, pinWithWinds(t, 1), pinWithWinds(t, 2), pinWithWinds(t, 3)},
		Draws:   []tile.TileID{draw},
		Rinshan: copies(t, 0, "1z"),
	}
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), play.KanAction(play.KanClosed, kanTile)))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	return g
}

func TestRiichi_WhenTheHandHasAClosedKanAndDrew_ShouldBeOfferedOnTheTenpaiKeepingDiscards(t *testing.T) {
	nineMan := tileOf(t, 0, "9m")
	g := dealerAfterClosedKan(t, copies(t, 0, "1111234567888m"), nineMan, tileOf(t, 0, "1m"))

	assertEqual(t, "riichis", riichis(g), riichiActions([]tile.TileID{nineMan, tileOf(t, 0, "1z")}))
}

func TestRiichi_WhenTheClosedKanHoldsEveryCopyOfTheOnlyWait_ShouldBeNeitherOfferedNorAccepted(t *testing.T) {
	dealer := slices.Concat(copies(t, 0, "555546m77s"), copies(t, 0, "23456p"))
	g := dealerAfterClosedKan(t, dealer, tileOf(t, 0, "7p"), tileOf(t, 0, "5m"))

	assertEqual(t, "riichis", riichis(g), []play.Action(nil))
	assertRefused(t, g, seat(t, 0), play.RiichiAction(tileOf(t, 0, "1z")), notOfferedRefusal())
}

func TestRiichi_WhenTheFirstDiscardFollowsAClosedKan_ShouldScoreRiichiAndIppatsuButNotDaburuRiichi(t *testing.T) {
	east := copies(t, 0, "1111z")
	riichiDiscard := tileOf(t, 0, "7z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(east, copies(t, 0, "123456789p")),
			copies(t, 0, "1123456788899m"),
			slices.Concat(copies(t, 2, "123456789s"), copies(t, 1, "5566z")),
			slices.Concat(copies(t, 3, "123456789s"), copies(t, 1, "234z"), copies(t, 3, "5z")),
		},
		Draws:   []tile.TileID{tileOf(t, 0, "2z"), riichiDiscard, tileOf(t, 2, "1m")},
		Rinshan: copies(t, 0, "3z"),
	}
	g, _ := script(t, begun(t, w, noStart()),
		act(seat(t, 0), play.KanAction(play.KanClosed, east[0])),
		act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "2z"))),
		act(seat(t, 1), play.RiichiAction(riichiDiscard)),
	)
	g, _ = discardDrawn(t, g, 1)

	_, events := script(t, g, act(seat(t, 1), play.RonAction()))

	yaku := firstWin(t, events).Yaku
	if !hasYaku(yaku, play.YakuRiichi) || !hasYaku(yaku, play.YakuIppatsu) || hasYaku(yaku, play.YakuDaburuRiichi) {
		t.Errorf("yaku = %v, want riichi and ippatsu without daburu riichi", yaku)
	}
}

func riichiDealerWall(t *testing.T, waitingHand []tile.TileID, drawnTile tile.TileID) testkit.StartWall {
	t.Helper()
	return testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{waitingHand, pinWithWinds(t, 1), pinWithWinds(t, 2), pinWithWinds(t, 3)},
		Draws: []tile.TileID{tileOf(t, 0, "5z"), tileOf(t, 0, "6z"), tileOf(t, 1, "6z"), tileOf(t, 2, "6z"), drawnTile},
	}
}

func riichiDealerAfterDraw(t *testing.T, w testkit.StartWall) game.Game {
	t.Helper()
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), play.RiichiAction(tileOf(t, 0, "5z"))))
	g, _ = discardDrawn(t, g, 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	return g
}

func assertClosedKanNotOfferedAndRefused(t *testing.T, waitingHand []tile.TileID, drawnTile, kanTile tile.TileID) {
	t.Helper()
	g := riichiDealerAfterDraw(t, riichiDealerWall(t, waitingHand, drawnTile))

	assertEqual(t, "kans", kans(g, seat(t, 0)), []play.Action(nil))
	assertRefused(t, g, seat(t, 0), play.KanAction(play.KanClosed, kanTile), notOfferedRefusal())
}

func TestClosedKan_WhenTheRiichiSeatHoldsThreeCopiesOfTheDrawnTile_ShouldBeNotOfferedAndRefused(t *testing.T) {
	drawnOneMan := tileOf(t, 2, "1m")

	assertClosedKanNotOfferedAndRefused(t, copies(t, 0, "11m123456789p12s"), drawnOneMan, drawnOneMan)
}

func TestClosedKan_WhenTheRiichiSeatQuadsATileHeldBeforeTheDraw_ShouldBeNotOfferedAndRefused(t *testing.T) {
	waitingHand := copies(t, 0, "111123m456789p5s")

	assertClosedKanNotOfferedAndRefused(t, waitingHand, tileOf(t, 0, "9s"), waitingHand[0])
}

func TestClosedKan_WhenTheRiichiKanNarrowsTheWaits_ShouldBeNotOfferedAndRefused(t *testing.T) {
	drawnEightMan := tileOf(t, 3, "8m")

	assertClosedKanNotOfferedAndRefused(t, copies(t, 0, "6888999m123p456s"), drawnEightMan, drawnEightMan)
}

func TestClosedKan_WhenTheRiichiKanBreaksTenpai_ShouldBeNotOfferedAndRefused(t *testing.T) {
	drawnFourMan := tileOf(t, 3, "4m")

	assertClosedKanNotOfferedAndRefused(t, copies(t, 0, "1113444556779m"), drawnFourMan, drawnFourMan)
}

func TestClosedKan_WhenTheRiichiKanTileIsAWait_ShouldBeNotOfferedAndRefused(t *testing.T) {
	drawnOneMan := tileOf(t, 3, "1m")

	assertClosedKanNotOfferedAndRefused(t, copies(t, 0, "1112344m123p456s"), drawnOneMan, drawnOneMan)
}

func TestClosedKan_WhenTheRiichiKanKeepsTheWaitsButLosesIipeikou_ShouldBeOfferedAndDeclared(t *testing.T) {
	waitingHand := copies(t, 0, "111222333m456p5s")
	drawnOneMan := tileOf(t, 3, "1m")
	w := riichiDealerWall(t, waitingHand, drawnOneMan)
	w.Rinshan = copies(t, 1, "5s")
	g := riichiDealerAfterDraw(t, w)

	assertEqual(t, "kans", kans(g, seat(t, 0)), []play.Action{play.KanAction(play.KanClosed, waitingHand[0])})

	g, events := script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, drawnOneMan)))

	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldClosedKan, Tiles: copies(t, 0, "1111m"),
	}}})
	if !containsAction(g.LegalActions(seat(t, 0)), play.TsumoAction()) {
		t.Error("tsumo on the rinshan tile is not offered")
	}
}
