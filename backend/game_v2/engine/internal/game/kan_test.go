package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func kans(g game.Game, s tile.Seat) []play.Action {
	var offered []play.Action
	for _, action := range g.LegalActions(s) {
		if action.Kind() == play.ActionKan {
			offered = append(offered, action)
		}
	}
	return offered
}

func filler(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "34579m345678s56z")
}

func kanFreeBystander(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "2468m123468p123z")
}

func gameOf(t *testing.T, hands [tile.SeatCount][]tile.TileID, draws []tile.TileID, w testkit.StartWall) game.Game {
	t.Helper()
	w.Hands, w.Draws = hands, draws
	return begun(t, w, noStart())
}

func dealerGame(t *testing.T, dealer, draws []tile.TileID, w testkit.StartWall) game.Game {
	t.Helper()
	return gameOf(t, [tile.SeatCount][]tile.TileID{dealer, filler(t, 1), filler(t, 2), filler(t, 3)}, draws, w)
}

func rinshanDraw(t *testing.T, n int, id tile.TileID) play.Drew {
	t.Helper()
	return play.Drew{Seat: seat(t, n), Tile: id, Rinshan: true}
}

type seatMeld struct {
	Seat tile.Seat
	Kind play.MeldKind
}

func meldKinds(events []play.Emitted) []seatMeld {
	var melds []seatMeld
	for _, called := range testkit.CalledMelds(events) {
		melds = append(melds, seatMeld{called.Seat, called.Meld.Kind})
	}
	return melds
}

func TestClosedKan_WhenASecondKanFollowsTheFirst_ShouldAllowItAndRevealANewDora(t *testing.T) {
	oneMan, twoMan := copies(t, 0, "1111m"), copies(t, 0, "2222m")
	rinshan, kanDora := copies(t, 0, "19p"), copies(t, 0, "78p")
	dealer := slices.Concat(oneMan, twoMan[:3], copies(t, 1, "12345p1s"))
	g := dealerGame(t, dealer, twoMan[3:], testkit.StartWall{Rinshan: rinshan, KanDora: kanDora})
	assertEqual(t, "kans", kans(g, seat(t, 0)), []play.Action{
		play.KanAction(play.KanClosed, oneMan[0]), play.KanAction(play.KanClosed, twoMan[0]),
	})

	g, first := script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, oneMan[2])))

	assertEqual(t, "first kinds", testkit.EventKinds(first),
		[]string{"called", "dora_revealed", "drew", "drew", "drew", "drew"})
	assertEqual(t, "first melds", testkit.CalledMelds(first), []play.Called{{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldClosedKan, Tiles: oneMan,
	}}})
	assertEqual(t, "first dora", testkit.DoraReveals(first), kanDora[:1])
	assertEqual(t, "first rinshan", testkit.DrawnRinshan(first), []play.Drew{rinshanDraw(t, 0, rinshan[0])})
	assertEqual(t, "context", turnContext(t, g), play.DecisionContext(play.TurnAfterDraw{Drawn: rinshan[0], Rinshan: true}))
	assertEqual(t, "kans left", kans(g, seat(t, 0)), []play.Action{play.KanAction(play.KanClosed, twoMan[0])})

	g, second := script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, twoMan[0])))

	assertEqual(t, "second dora", testkit.DoraReveals(second), kanDora[1:2])
	assertEqual(t, "second rinshan", testkit.DrawnRinshan(second), []play.Drew{rinshanDraw(t, 0, rinshan[1])})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	assertOwnership(t, g)
}

func TestKanOffers_WhenTheHandHoldsThreeQuads_ShouldListOneClosedKanPerKindAndAcceptAnyCopy(t *testing.T) {
	hand := copies(t, 0, "1111222233334p")
	g := dealerGame(t, hand, copies(t, 1, "4p"), testkit.StartWall{})

	assertEqual(t, "kans", kans(g, seat(t, 0)), []play.Action{
		play.KanAction(play.KanClosed, hand[0]), play.KanAction(play.KanClosed, hand[4]),
		play.KanAction(play.KanClosed, hand[8]),
	})

	_, events := script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, hand[5])))

	assertEqual(t, "melds", meldKinds(events), []seatMeld{{seat(t, 0), play.MeldClosedKan}})
	assertEqual(t, "kan tiles", testkit.CalledMelds(events)[0].Meld.Tiles, hand[4:8])
}

func TestClosedKan_WhenTheSeatHoldsThreeCopies_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	triplet := copies(t, 0, "111m")
	build := func() game.Game {
		return dealerGame(t, slices.Concat(triplet, copies(t, 0, "123456789p1s")), copies(t, 0, "1z"), testkit.StartWall{})
	}

	assertEqual(t, "kans", kans(build(), seat(t, 0)), []play.Action(nil))
	assertRefused(t, build, seat(t, 0), play.KanAction(play.KanClosed, triplet[0]), notOfferedRefusal())
}

func TestKan_WhenASeatDeclaresOutOfTurn_ShouldBeRefusedAsNotAwaited(t *testing.T) {
	build := func() game.Game {
		dealer := slices.Concat(copies(t, 0, "1111m"), copies(t, 0, "123456789p"))
		return dealerGame(t, dealer, copies(t, 0, "1z"), testkit.StartWall{})
	}
	ownTile := build().Hand(seat(t, 1))[0]

	for _, kind := range []play.KanKind{play.KanClosed, play.KanAdded} {
		assertRefused(t, build, seat(t, 1), play.KanAction(kind, ownTile), seatNotAwaitedRefusal())
	}
}

func TestClosedKan_WhenOneLiveTileIsLeft_ShouldBeOfferedWithANonHaiteiRinshanDraw(t *testing.T) {
	quad := copies(t, 0, "1111m")
	g := dealerGame(t, slices.Concat(quad, copies(t, 0, "123456789p")), nil, testkit.StartWall{})
	g = playDefaultsWhileLiveTilesExceed(t, g, 1)
	assertEqual(t, "awaiting and live tiles", [2]any{g.Awaiting(), g.LiveTiles()}, [2]any{awaitingTurn(seat(t, 0)), 1})
	if !containsAction(kans(g, seat(t, 0)), play.KanAction(play.KanClosed, quad[0])) {
		t.Errorf("kans = %v, want the closed kan of 1m", kans(g, seat(t, 0)))
	}

	g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, quad[0])))

	assertEqual(t, "live tiles", g.LiveTiles(), 0)
	if draw, ok := turnContext(t, g).(play.TurnAfterDraw); !ok || !draw.Rinshan || draw.Haitei {
		t.Errorf("context = %+v, want a rinshan draw that is not haitei", turnContext(t, g))
	}
}

func seatOnePonOfDealerFirstDiscard(t *testing.T) (game.Game, []tile.TileID) {
	t.Helper()
	oneMan := copies(t, 0, "1111m")
	g := gameOf(t, [tile.SeatCount][]tile.TileID{
		slices.Concat(copies(t, 1, "123456789p"), copies(t, 0, "2345z")),
		slices.Concat(oneMan[:3], copies(t, 0, "123456789p1z")),
		filler(t, 2),
		filler(t, 3),
	}, oneMan[3:], testkit.StartWall{})
	g, _ = discardDrawn(t, g, 1)
	pon := firstPon(t, g, seat(t, 1))
	assertEqual(t, "offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.KanAction(play.KanOpen, oneMan[3]), pon, play.PassAction()})
	g, _ = script(t, g, act(seat(t, 1), pon), act(seat(t, 1), play.DiscardAction(tileOf(t, 0, "1z"))))
	return g, oneMan
}

func TestAddedKan_WhenOneLiveTileIsLeft_ShouldBeOffered(t *testing.T) {
	g, oneMan := seatOnePonOfDealerFirstDiscard(t)

	g = playDefaultsWhileLiveTilesExceed(t, g, 1)

	assertEqual(t, "awaiting and live tiles", [2]any{g.Awaiting(), g.LiveTiles()}, [2]any{awaitingTurn(seat(t, 1)), 1})
	assertEqual(t, "kans", kans(g, seat(t, 1)), []play.Action{play.KanAction(play.KanAdded, oneMan[2])})
}

func TestClosedKan_WhenTheLiveWallIsEmpty_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	quad := copies(t, 0, "1111m")
	build := func() game.Game {
		g := gameOf(t, [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789p1234z"),
			slices.Concat(quad, copies(t, 1, "123456789p")),
			filler(t, 2),
			filler(t, 3),
		}, nil, testkit.StartWall{})
		return playDefaultsWhileLiveTilesExceed(t, g, 0)
	}
	g := build()
	assertEqual(t, "awaiting and live tiles", [2]any{g.Awaiting(), g.LiveTiles()}, [2]any{awaitingTurn(seat(t, 1)), 0})

	assertEqual(t, "kans", kans(g, seat(t, 1)), []play.Action(nil))
	assertRefused(t, build, seat(t, 1), play.KanAction(play.KanClosed, quad[0]), notOfferedRefusal())
}

func onePonAndFourthCopy(t *testing.T) (game.Game, []tile.TileID) {
	t.Helper()
	oneMan := copies(t, 0, "1111m")
	dealer := slices.Concat(oneMan[:2], copies(t, 0, "123456789s"), copies(t, 0, "77z"))
	g := dealerPonFromSeatThree(t, dealer, oneMan[2], tileOf(t, 0, "7z"),
		slices.Concat(copies(t, 0, "666z"), oneMan[3:]), play.Option[tile.TileID]{})
	return g, oneMan
}

func TestAddedKan_WhenThePonSeatDrawsTheFourthCopy_ShouldBeOffered(t *testing.T) {
	g, oneMan := onePonAndFourthCopy(t)

	g, _ = discardDrawn(t, g, 3)

	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	assertEqual(t, "kans", kans(g, seat(t, 0)), []play.Action{play.KanAction(play.KanAdded, oneMan[3])})
}

func TestAddedKan_WhenNoSeatMayRobIt_ShouldUpgradeThePonToAnAddedKanAndDrawTheRinshan(t *testing.T) {
	g, oneMan := onePonAndFourthCopy(t)
	g, _ = discardDrawn(t, g, 3)

	g, events := script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, oneMan[0])))

	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldAddedKan, Tiles: oneMan, Called: play.Some(oneMan[2]), From: play.Some(seat(t, 3)), Added: play.Some(oneMan[3]),
	}}})
	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called", "drew", "drew", "drew", "drew"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	if slices.Contains(g.Hand(seat(t, 0)), oneMan[3]) {
		t.Error("the added copy is still in the hand")
	}
	assertOwnership(t, g)
}

func fivePinPonBySeatOne(t *testing.T, rest []tile.TileID) game.Game {
	t.Helper()
	fivePin := copies(t, 0, "5555p")
	g := gameOf(t, [tile.SeatCount][]tile.TileID{
		slices.Concat(fivePin[2:3], copies(t, 0, "123456789s123z")),
		slices.Concat(fivePin[:2], rest),
		copies(t, 1, "123456789m2345z"),
		copies(t, 2, "123456789m2345z"),
	}, slices.Concat(copies(t, 0, "4z"), copies(t, 0, "7777z")), testkit.StartWall{})
	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(fivePin[2])))
	g, _ = script(t, g, act(seat(t, 1), firstPon(t, g, seat(t, 1))), act(seat(t, 1), play.DiscardAction(tileOf(t, 0, "5z"))))
	g, _ = discardDrawn(t, g, 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	return g
}

func TestAddedKan_WhenTheSeatHoldsATripletButNoPon_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	fivePin := copies(t, 0, "5555p")
	build := func() game.Game {
		hand := slices.Concat(fivePin[:2], fivePin[3:], copies(t, 0, "123456789m5z"))
		g := gameOf(t, [tile.SeatCount][]tile.TileID{copies(t, 0, "123456789s1234z"), hand, filler(t, 2), filler(t, 3)},
			[]tile.TileID{tileOf(t, 1, "1z"), tileOf(t, 1, "7z")}, testkit.StartWall{})
		g, _ = discardDrawn(t, g, 1)
		return g
	}
	assertEqual(t, "awaiting", build().Awaiting(), awaitingTurn(seat(t, 1)))

	assertRefused(t, build, seat(t, 1), play.KanAction(play.KanAdded, fivePin[0]), notOfferedRefusal())
}

func TestAddedKan_WhenTheSeatHoldsNoFourthCopy_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	build := func() game.Game { return fivePinPonBySeatOne(t, copies(t, 0, "123456789m56z")) }

	assertEqual(t, "kans", kans(build(), seat(t, 1)), []play.Action(nil))
	assertRefused(t, build, seat(t, 1), play.KanAction(play.KanAdded, tileOf(t, 3, "5p")), notOfferedRefusal())
}

func TestAddedKan_WhenTheTileIDNamesAMeldedCopy_ShouldKanTheCopyInHand(t *testing.T) {
	fivePin := copies(t, 0, "5555p")
	g := fivePinPonBySeatOne(t, slices.Concat(fivePin[3:], copies(t, 0, "12345678m56z")))

	g, events := script(t, g, act(seat(t, 1), play.KanAction(play.KanAdded, fivePin[0])))

	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 1), Meld: play.MeldView{
		Kind: play.MeldAddedKan, Tiles: fivePin, Called: play.Some(fivePin[2]), From: play.Some(seat(t, 0)), Added: play.Some(fivePin[3]),
	}}})
	if slices.Contains(g.Hand(seat(t, 1)), fivePin[3]) {
		t.Error("the fourth copy is still in the hand")
	}
}

func TestAddedKan_WhenTheSeatIsInRiichi_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	oneMan := copies(t, 0, "1111m")
	build := func() game.Game {
		dealer := slices.Concat(oneMan[:3], copies(t, 0, "456789p2345s"))
		g := gameOf(t, [tile.SeatCount][]tile.TileID{
			dealer, kanFreeBystander(t, 1), kanFreeBystander(t, 2), kanFreeBystander(t, 3),
		}, slices.Concat(copies(t, 0, "567z"), copies(t, 1, "6z"), oneMan[3:]), testkit.StartWall{})
		g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(tileOf(t, 0, "5z"))))
		g, _ = discardDrawn(t, g, 3)
		return g
	}
	drawn, _ := testkit.Drawn(build())
	assertEqual(t, "drawn", drawn, oneMan[3])

	assertEqual(t, "kans", kans(build(), seat(t, 0)), []play.Action{play.KanAction(play.KanClosed, oneMan[0])})
	assertRefused(t, build, seat(t, 0), play.KanAction(play.KanAdded, oneMan[3]), notOfferedRefusal())
}

func TestKan_WhenTheTurnFollowsACall_ShouldOfferNeitherAClosedNorAnAddedKanAndRefuseBoth(t *testing.T) {
	oneMan, twoMan := copies(t, 0, "1111m"), copies(t, 0, "2222m")
	chiPair := [2]tile.TileID{tileOf(t, 0, "1p"), tileOf(t, 0, "2p")}
	beforeChi := func() game.Game {
		dealer := slices.Concat(oneMan[:3], twoMan, copies(t, 0, "12p"), copies(t, 0, "9s"), copies(t, 0, "567z"))
		g := dealerPonFromSeatThree(t, dealer, oneMan[3], tileOf(t, 0, "9s"),
			[]tile.TileID{tileOf(t, 1, "6z"), tileOf(t, 2, "6z"), tileOf(t, 0, "3p")}, play.Option[tile.TileID]{})
		g, _ = discardDrawn(t, g, 3)
		return g
	}
	assertEqual(t, "offers", beforeChi().LegalActions(seat(t, 0)), []play.Action{play.ChiAction(chiPair), play.PassAction()})
	build := func() game.Game {
		g, _ := script(t, beforeChi(), act(seat(t, 0), play.ChiAction(chiPair)))
		return g
	}

	if _, ok := turnContext(t, build()).(play.TurnAfterCall); !ok {
		t.Errorf("context = %+v, want a turn after a call", turnContext(t, build()))
	}
	assertEqual(t, "kans", kans(build(), seat(t, 0)), []play.Action(nil))
	for _, action := range []play.Action{play.KanAction(play.KanClosed, twoMan[0]), play.KanAction(play.KanAdded, oneMan[2])} {
		assertRefused(t, build, seat(t, 0), action, notOfferedRefusal())
	}
}

func TestTsumo_WhenTheOpenKansRinshanCompletesTheHand_ShouldBeOfferedAndAccepted(t *testing.T) {
	oneMan := copies(t, 0, "1111m")
	tanki, rinshanFiveSou := tileOf(t, 0, "5s"), tileOf(t, 1, "5s")
	g := gameOf(t, [tile.SeatCount][]tile.TileID{
		slices.Concat(copies(t, 0, "1234567z"), copies(t, 1, "123456z")),
		slices.Concat(oneMan[:3], copies(t, 0, "234567p789s"), []tile.TileID{tanki}),
		copies(t, 2, "456789m1234567z")[:13],
		copies(t, 3, "456789m1234567z")[:13],
	}, oneMan[3:], testkit.StartWall{Rinshan: []tile.TileID{rinshanFiveSou}})
	g, _ = discardDrawn(t, g, 1)
	assertEqual(t, "offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.KanAction(play.KanOpen, oneMan[3]), firstPon(t, g, seat(t, 1)), play.PassAction()})

	g, events := script(t, g, act(seat(t, 1), play.KanAction(play.KanOpen, oneMan[0])))

	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 1), Meld: play.MeldView{
		Kind: play.MeldOpenKan, Tiles: oneMan, Called: play.Some(oneMan[3]), From: play.Some(seat(t, 0)),
	}}})
	assertEqual(t, "rinshan", testkit.DrawnRinshan(events), []play.Drew{rinshanDraw(t, 1, rinshanFiveSou)})
	if !containsAction(g.LegalActions(seat(t, 1)), play.TsumoAction()) {
		t.Error("tsumo on the rinshan tile is not offered")
	}

	_, events = script(t, g, act(seat(t, 1), play.TsumoAction()))

	win := firstWin(t, events)
	assertEqual(t, "winner and loser", [2]any{win.Winner, win.Loser}, [2]any{seat(t, 1), play.Option[tile.Seat]{}})
	if !slices.Contains(win.Yaku, play.YakuRinshan) {
		t.Errorf("yaku = %v, want rinshan", win.Yaku)
	}
}

func TestCallPrompt_WhenAnOpenKanIsDeclaredOnTheLastLiveTile_ShouldResolveTheKan(t *testing.T) {
	fiveMan := copies(t, 0, "5555m")
	g := gameOf(t, [tile.SeatCount][]tile.TileID{
		slices.Concat(fiveMan[:1], copies(t, 0, "123456789p123z")),
		slices.Concat(fiveMan[1:], copies(t, 0, "123456789s5z")),
		copies(t, 1, "123456789p1234z"),
		slices.Concat(copies(t, 1, "123456789s"), copies(t, 2, "1234z")),
	}, nil, testkit.StartWall{})
	g = playDefaultsWhileLiveTilesExceed(t, g, 1)
	assertEqual(t, "awaiting and live tiles", [2]any{g.Awaiting(), g.LiveTiles()}, [2]any{awaitingTurn(seat(t, 0)), 1})
	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(fiveMan[0])))
	assertEqual(t, "offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.KanAction(play.KanOpen, fiveMan[0]), firstPon(t, g, seat(t, 1)), play.PassAction()})

	g, events := script(t, g, act(seat(t, 1), play.KanAction(play.KanOpen, fiveMan[0])))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called", "drew", "drew", "drew", "drew"})
	assertEqual(t, "melds", meldKinds(events), []seatMeld{{seat(t, 1), play.MeldOpenKan}})
	assertEqual(t, "live tiles", g.LiveTiles(), 0)
}

func TestCallPrompt_WhenAnOpenKanAndAChiAreDeclared_ShouldMakeTheKan(t *testing.T) {
	fiveMan := tileOf(t, 0, "5m")
	g := gameOf(t, [tile.SeatCount][]tile.TileID{
		copies(t, 0, "123456789p1234z"),
		copies(t, 0, "46m123456789s56z"),
		copies(t, 1, "123456789p1234z"),
		slices.Concat(copies(t, 1, "555m"), copies(t, 1, "123456789s"), copies(t, 0, "7z")),
	}, []tile.TileID{fiveMan}, testkit.StartWall{})
	g, _ = discardDrawn(t, g, 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 3)))
	assertEqual(t, "offers", g.LegalActions(seat(t, 3)),
		[]play.Action{play.KanAction(play.KanOpen, fiveMan), firstPon(t, g, seat(t, 3)), play.PassAction()})

	g, _ = script(t, g, act(seat(t, 1), play.ChiAction([2]tile.TileID{tileOf(t, 0, "4m"), tileOf(t, 0, "6m")})))
	g, events := script(t, g, act(seat(t, 3), play.KanAction(play.KanOpen, fiveMan)))

	assertEqual(t, "melds", meldKinds(events), []seatMeld{{seat(t, 3), play.MeldOpenKan}})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 3)))
}

func TestChankanPass_WhenARiichiSeatPasses_ShouldSetItsRiichiFuriten(t *testing.T) {
	threePin := copies(t, 0, "3333p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(threePin[:2], copies(t, 3, "123456789s"), copies(t, 1, "57z")),
			slices.Concat(copies(t, 0, "123456789m45p9s"), copies(t, 2, "1z")),
			copies(t, 1, "123456789s1234z")[:13],
			slices.Concat(threePin[2:3], copies(t, 2, "123456789m2345z")[:12]),
		},
		Draws: slices.Concat(copies(t, 0, "1234z"),
			[]tile.TileID{tileOf(t, 2, "9s"), tileOf(t, 1, "6z"), tileOf(t, 2, "6z"), threePin[3]},
			[]tile.TileID{tileOf(t, 3, "6z"), tileOf(t, 0, "6p")}),
		Rinshan: copies(t, 0, "7z"),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 3)
	g, _ = script(t, g, act(seat(t, 3), play.DiscardAction(threePin[2])))
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(tileOf(t, 1, "5z"))))
	g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(tileOf(t, 2, "1z"))))
	g, _ = discardDrawn(t, g, 2)
	drawn, _ := testkit.Drawn(g)
	assertEqual(t, "drawn", drawn, threePin[3])
	g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, threePin[3])))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))

	g, passed := script(t, g, act(seat(t, 1), play.PassAction()))

	assertEqual(t, "furiten", testkit.FuritenChanges(passed), []play.FuritenChanged{{Seat: seat(t, 1), Furiten: true}})
	g, _ = discardDrawn(t, g, 2)
	g, sixPinDiscard := discardDrawn(t, g, 1)
	assertEqual(t, "six pin discard", testkit.EventKinds(sixPinDiscard)[0], "discarded")
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 3)))
}

func TestFourKans_WhenOneSeatDeclaresAllFour_ShouldNotAbort(t *testing.T) {
	fiveMan := copies(t, 0, "5555m")
	loneChun := tileOf(t, 0, "7z")
	g := gameOf(t, [tile.SeatCount][]tile.TileID{
		slices.Concat(copies(t, 0, "1111s9999s4444z"), fiveMan[:1]),
		kanFreeBystander(t, 1), kanFreeBystander(t, 2), kanFreeBystander(t, 3),
	}, fiveMan[1:2], testkit.StartWall{Rinshan: []tile.TileID{fiveMan[2], fiveMan[3], loneChun, tileOf(t, 0, "9m")}})
	for _, kan := range []string{"1s", "9s", "4z", "5m"} {
		g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, tileOf(t, 0, kan))))
	}

	g, events := script(t, g, act(seat(t, 0), play.DiscardAction(loneChun)))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"discarded", "drew", "drew", "drew", "drew"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
}

func TestAddedKan_WhenTheTableHoldsFourKans_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	fivePin, fourSou := copies(t, 0, "5555p"), copies(t, 0, "4444s")
	pon := play.PonAction([2]tile.TileID{fivePin[0], fivePin[1]})
	beforePon := func() game.Game {
		g := gameOf(t, [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 0, "1111s2222s3333s"), copies(t, 0, "7z")),
			slices.Concat(fivePin[:3], copies(t, 0, "123456789m1z")),
			copies(t, 1, "123456789m2345z"),
			copies(t, 2, "123456789m2345z"),
		}, slices.Concat(fourSou[:1], copies(t, 0, "666z"), copies(t, 2, "1z")),
			testkit.StartWall{Rinshan: slices.Concat(fourSou[1:], fivePin[3:])})
		for _, kan := range []string{"1s", "2s", "3s", "4s"} {
			g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, tileOf(t, 0, kan))))
		}
		g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(fivePin[3])))
		return g
	}
	assertEqual(t, "offers", beforePon().LegalActions(seat(t, 1)),
		[]play.Action{pon, play.PonAction([2]tile.TileID{fivePin[1], fivePin[2]}), play.PassAction()})
	build := func() game.Game {
		g, _ := script(t, beforePon(), act(seat(t, 1), pon), act(seat(t, 1), play.DiscardAction(tileOf(t, 0, "1z"))))
		g, _ = discardDrawn(t, g, 3)
		return g
	}
	assertEqual(t, "awaiting", build().Awaiting(), awaitingTurn(seat(t, 1)))

	assertEqual(t, "kans", kans(build(), seat(t, 1)), []play.Action(nil))
	assertRefused(t, build, seat(t, 1), play.KanAction(play.KanAdded, fivePin[2]), notOfferedRefusal())
}

type threeKans struct {
	eastExtras, westHand, northHand []tile.TileID
	westDraw                        tile.TileID
	northDraws                      []tile.TileID
}

func eightPin(t *testing.T, first int) tile.TileID {
	t.Helper()
	return tileOf(t, first, "8p")
}

func fourKansDora(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 3, "1235z")
}

func threeKansOnTable(t *testing.T, table threeKans) game.Game {
	t.Helper()
	seatZero := slices.Concat(copies(t, 0, "1111s9999s"), []tile.TileID{eightPin(t, 1), eightPin(t, 2)}, table.eastExtras,
		[]tile.TileID{tileOf(t, 0, "7z")})
	seatOne := slices.Concat(copies(t, 0, "4444z"), copies(t, 0, "13579p2468s"))
	w := testkit.StartWall{
		Hands:   [tile.SeatCount][]tile.TileID{seatZero, seatOne, table.westHand, table.northHand},
		Draws:   slices.Concat([]tile.TileID{tileOf(t, 1, "7z"), tileOf(t, 1, "1z"), table.westDraw}, table.northDraws),
		Rinshan: []tile.TileID{tileOf(t, 2, "7z"), tileOf(t, 0, "9m"), tileOf(t, 1, "9m"), eightPin(t, 3)},
		KanDora: fourKansDora(t),
	}
	g := begun(t, w, noStart())
	for _, kan := range []string{"1s", "9s"} {
		g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, tileOf(t, 0, kan))))
	}
	g, _ = script(t, g,
		act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "9m"))),
		act(seat(t, 1), play.KanAction(play.KanClosed, tileOf(t, 0, "4z"))),
		act(seat(t, 1), play.DiscardAction(tileOf(t, 1, "9m"))),
	)
	return g
}

func seatThreeCore(t *testing.T) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 2, "234m567p345s"), []tile.TileID{eightPin(t, 0)})
}

func seatTwoJunk(t *testing.T) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 1, "13579p2468s"), copies(t, 0, "136z"))
}

func ronnableReplacementDiscard(t *testing.T) game.Game {
	t.Helper()
	fiveMan := copies(t, 0, "5555m")
	g := threeKansOnTable(t, threeKans{
		eastExtras: copies(t, 0, "22m"),
		westHand:   slices.Concat(seatTwoJunk(t), copies(t, 0, "2z")),
		northHand:  slices.Concat(seatThreeCore(t), fiveMan[:3]),
		westDraw:   tileOf(t, 1, "2z"),
		northDraws: fiveMan[3:],
	})
	g, _ = discardDrawn(t, g, 1)

	g, kan := script(t, g, act(seat(t, 3), play.KanAction(play.KanClosed, fiveMan[3])))
	assertEqual(t, "kan kinds", testkit.EventKinds(kan), []string{"called", "dora_revealed", "drew", "drew", "drew", "drew"})
	g, _ = script(t, g, act(seat(t, 3), play.DiscardAction(eightPin(t, 0))))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))
	assertEqual(t, "offers", g.LegalActions(seat(t, 0)), []play.Action{play.RonAction(), play.PassAction()})
	return g
}

func TestFourKans_WhenTheReplacementDiscardIsRonned_ShouldScoreTheRon(t *testing.T) {
	_, events := script(t, ronnableReplacementDiscard(t), act(seat(t, 0), play.RonAction()))

	win := firstWin(t, events)
	assertEqual(t, "winner and loser", [2]any{win.Winner, win.Loser}, [2]any{seat(t, 0), play.Some(seat(t, 3))})
}

func TestFourKans_WhenTheRonCallerPassesTheReplacementDiscard_ShouldAbort(t *testing.T) {
	g, events := script(t, ronnableReplacementDiscard(t), act(seat(t, 0), play.PassAction()))

	assertEqual(t, "result", roundResult(t, events), play.RoundResult(play.Abortive{Kind: play.FourKans{}}))
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
}

func TestFourKans_WhenTheOpenFourthKansReplacementDiscardPasses_ShouldRevealTheKanDoraThenAbort(t *testing.T) {
	fiveMan := copies(t, 0, "5555m")
	g := threeKansOnTable(t, threeKans{
		eastExtras: copies(t, 0, "24m"),
		westHand:   slices.Concat(seatTwoJunk(t), fiveMan[:1]),
		northHand:  slices.Concat(seatThreeCore(t), fiveMan[1:]),
		westDraw:   tileOf(t, 0, "2z"),
	})
	g, _ = script(t, g, act(seat(t, 2), play.DiscardAction(fiveMan[0])))

	g, kan := script(t, g, act(seat(t, 3), play.KanAction(play.KanOpen, fiveMan[0])))

	assertEqual(t, "kan kinds", testkit.EventKinds(kan), []string{"called", "drew", "drew", "drew", "drew"})
	assertEqual(t, "rinshan", testkit.DrawnRinshan(kan), []play.Drew{rinshanDraw(t, 3, eightPin(t, 3))})
	if !containsAction(g.LegalActions(seat(t, 3)), play.TsumoAction()) {
		t.Error("tsumo on the rinshan tile is not offered")
	}

	_, discard := script(t, g, act(seat(t, 3), play.DiscardAction(eightPin(t, 0))))

	assertEqual(t, "discard kinds", testkit.EventKinds(discard), []string{"discarded", "dora_revealed", "round_ended"})
	assertEqual(t, "dora", testkit.DoraReveals(discard), fourKansDora(t)[3:])
	assertEqual(t, "result", roundResult(t, discard), play.RoundResult(play.Abortive{Kind: play.FourKans{}}))
}

func TestFourKans_WhenTheChankanOnTheFourthKanIsDeclined_ShouldDrawTheRinshanThenAbortAtTheDiscard(t *testing.T) {
	fiveMan := copies(t, 0, "5555m")
	g := threeKansOnTable(t, threeKans{
		eastExtras: copies(t, 1, "46m"),
		westHand:   slices.Concat(seatTwoJunk(t), fiveMan[:1]),
		northHand:  slices.Concat(seatThreeCore(t), fiveMan[1:3], copies(t, 0, "7s")),
		westDraw:   tileOf(t, 0, "2z"),
		northDraws: []tile.TileID{tileOf(t, 1, "2z"), tileOf(t, 2, "2z"), tileOf(t, 1, "6z"), fiveMan[3]},
	})
	g, _ = script(t, g, act(seat(t, 2), play.DiscardAction(fiveMan[0])))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0), seat(t, 3)))
	g, _ = script(t, g,
		act(seat(t, 0), play.PassAction()),
		act(seat(t, 3), firstPon(t, g, seat(t, 3))),
		act(seat(t, 3), play.DiscardAction(tileOf(t, 0, "7s"))),
	)
	g, _ = discardDrawn(t, g, 3)
	g, _ = script(t, g, act(seat(t, 3), play.KanAction(play.KanAdded, fiveMan[3])))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))

	g, declined := script(t, g, act(seat(t, 0), play.PassAction()))

	assertEqual(t, "declined kinds", testkit.EventKinds(declined)[:4], []string{"drew", "drew", "drew", "drew"})
	assertEqual(t, "declined dora", testkit.DoraReveals(declined), []tile.TileID(nil))
	assertEqual(t, "phase", g.Phase(), play.PhasePlaying)

	_, discard := script(t, g, act(seat(t, 3), play.DiscardAction(eightPin(t, 0))))

	assertEqual(t, "dora", testkit.DoraReveals(discard), fourKansDora(t)[3:])
	assertEqual(t, "result", roundResult(t, discard), play.RoundResult(play.Abortive{Kind: play.FourKans{}}))
}
