package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func notOfferedRefusal() play.Refusal {
	return refusal(play.RefusalNotOffered, play.CodeNotOffered)
}

func fourManChiPair(t *testing.T) [2]tile.TileID {
	t.Helper()
	return [2]tile.TileID{tileOf(t, 0, "5m"), tileOf(t, 0, "6m")}
}

func fourManDiscarded(t *testing.T) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789p1234z"),
			copies(t, 0, "567m123456789s5z"),
			slices.Concat(copies(t, 1, "44m"), copies(t, 1, "123456789s56z")),
			copies(t, 1, "123456789p1234z"),
		},
		Draws: slices.Concat([]tile.TileID{tileOf(t, 0, "4m")}, copies(t, 0, "7777z")),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2)))
	assertEqual(t, "chi seat offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.ChiAction(fourManChiPair(t)), play.PassAction()})
	assertEqual(t, "pon seat offers", g.LegalActions(seat(t, 2)),
		[]play.Action{firstPon(t, g, seat(t, 2)), play.PassAction()})
	return g
}

func fourManChied(t *testing.T) (game.Game, []play.Emitted) {
	t.Helper()
	return script(t, fourManDiscarded(t),
		act(seat(t, 2), play.PassAction()),
		act(seat(t, 1), play.ChiAction(fourManChiPair(t))),
	)
}

func TestKuikae_WhenPon_ShouldForbidTheCalledKind(t *testing.T) {
	g := fourManDiscarded(t)
	pon := firstPon(t, g, seat(t, 2))

	g, _ = script(t, g, act(seat(t, 1), play.PassAction()), act(seat(t, 2), pon))

	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	assertEqual(t, "context", turnContext(t, g), play.DecisionContext(play.TurnAfterCall{
		Kuikae: []tile.Kind{kindOf(t, "4m")},
	}))
}

func TestKuikaeSuji_WhenChiOfTheLowestTile_ShouldForbidTheSujiTile(t *testing.T) {
	g, events := fourManChied(t)

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called"})
	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 1), Meld: play.MeldView{
		Kind:   play.MeldChi,
		Tiles:  []tile.TileID{tileOf(t, 0, "4m"), tileOf(t, 0, "5m"), tileOf(t, 0, "6m")},
		Called: play.Some(tileOf(t, 0, "4m")),
		From:   play.Some(seat(t, 0)),
	}}})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	assertEqual(t, "context", turnContext(t, g), play.DecisionContext(play.TurnAfterCall{
		Kuikae: []tile.Kind{kindOf(t, "4m"), kindOf(t, "7m")},
	}))
	if containsAction(g.LegalActions(seat(t, 1)), play.DiscardAction(tileOf(t, 0, "7m"))) {
		t.Error("the suji tile is offered as a discard")
	}
}

func TestKuikaeSuji_WhenTheSujiTileIsDiscardedAfterChi_ShouldBeRefusedByRuleAndChangeNothing(t *testing.T) {
	build := func() game.Game {
		g, _ := fourManChied(t)
		return g
	}

	assertRefused(t, build, seat(t, 1), play.DiscardAction(tileOf(t, 0, "7m")), refusal(play.RefusalRule, play.CodeKuikae))
}

func TestKuikae_WhenThePlayerDiscards_ShouldClearTheRestriction(t *testing.T) {
	g, _ := fourManChied(t)

	g, discarded := script(t, g, act(seat(t, 1), play.DiscardAction(tileOf(t, 0, "5z"))))
	if d, ok := discarded[0].Event.(play.Discarded); !ok || d.Seat != seat(t, 1) || d.Tsumogiri {
		t.Errorf("first event = %+v, want seat 1's hand discard", discarded[0].Event)
	}
	g, _ = discardDrawn(t, g, 3)

	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	if _, ok := turnContext(t, g).(play.TurnAfterDraw); !ok {
		t.Errorf("context = %+v, want a turn after a draw", turnContext(t, g))
	}
	if !containsAction(g.LegalActions(seat(t, 1)), play.DiscardAction(tileOf(t, 0, "7m"))) {
		t.Error("the suji tile is still forbidden")
	}
}

func TestTsumo_WhenRightAfterTheSeatsOwnCall_ShouldBeNeitherOfferedNorAcceptedUntilTheNextDraw(t *testing.T) {
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789p1234z"),
			slices.Concat(copies(t, 0, "234567m23455s"), copies(t, 0, "77z")),
			copies(t, 1, "123456789p1234z"),
			copies(t, 2, "123456789p1234z"),
		},
		Draws: slices.Concat(copies(t, 2, "7z"), copies(t, 0, "666z"), copies(t, 2, "5s")),
	}
	build := func() game.Game {
		g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
		g, _ = script(t, g, act(seat(t, 1), firstPon(t, g, seat(t, 1))))
		return g
	}
	g := build()

	if containsAction(g.LegalActions(seat(t, 1)), play.TsumoAction()) {
		t.Error("tsumo is offered right after the call")
	}
	assertRefused(t, build, seat(t, 1), play.TsumoAction(), notOfferedRefusal())

	g, _ = script(t, g, act(seat(t, 1), play.DiscardAction(tileOf(t, 1, "5s"))))
	g, _ = discardDrawn(t, g, 3)
	if !containsAction(g.LegalActions(seat(t, 1)), play.TsumoAction()) {
		t.Error("tsumo is not offered after the next draw")
	}
	_, events := script(t, g, act(seat(t, 1), play.TsumoAction()))
	tsumo, ok := roundResult(t, events).(play.Tsumo)
	if !ok || len(tsumo.Win.Melds) != 1 || tsumo.Win.Melds[0].Kind != play.MeldPon {
		t.Errorf("result = %+v, want a tsumo with one pon", roundResult(t, events))
	}
}

func nineManDiscarded(t *testing.T, hands [tile.SeatCount][]tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{Hands: hands, Draws: []tile.TileID{tileOf(t, 0, "9m")}}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	return g
}

func nineManPonAndChiSeats(t *testing.T) game.Game {
	t.Helper()
	g := nineManDiscarded(t, [tile.SeatCount][]tile.TileID{
		copies(t, 0, "123456789s1234z"),
		slices.Concat(copies(t, 0, "678m159p567z"), copies(t, 1, "1234z")),
		slices.Concat(copies(t, 1, "999m"), copies(t, 1, "123456789s5z")),
		slices.Concat(copies(t, 2, "1234567z"), copies(t, 1, "234678p")),
	})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2)))
	assertEqual(t, "chi seat offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.ChiAction([2]tile.TileID{tileOf(t, 0, "7m"), tileOf(t, 0, "8m")}), play.PassAction()})
	assertEqual(t, "pon seat offers", g.LegalActions(seat(t, 2)), []play.Action{
		play.KanAction(play.KanOpen, tileOf(t, 0, "9m")), firstPon(t, g, seat(t, 2)), play.PassAction(),
	})
	return g
}

func TestResolveCall_WhenPonIsDeclared_ShouldEmitTheMeldThenATurnForbiddingTheCalledKind(t *testing.T) {
	g := nineManDiscarded(t, [tile.SeatCount][]tile.TileID{
		copies(t, 0, "123456789p1234z"),
		copies(t, 1, "123456789p1234z"),
		slices.Concat(copies(t, 1, "99m"), copies(t, 0, "123456789s56z")),
		slices.Concat(copies(t, 1, "123456789s"), copies(t, 2, "1234z")),
	})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 2)))
	pon := firstPon(t, g, seat(t, 2))
	assertEqual(t, "offers", g.LegalActions(seat(t, 2)), []play.Action{pon, play.PassAction()})

	g, events := script(t, g, act(seat(t, 2), pon))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called"})
	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 2), Meld: play.MeldView{
		Kind:   play.MeldPon,
		Tiles:  []tile.TileID{tileOf(t, 0, "9m"), tileOf(t, 1, "9m"), tileOf(t, 2, "9m")},
		Called: play.Some(tileOf(t, 0, "9m")),
		From:   play.Some(seat(t, 0)),
	}}})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	assertEqual(t, "context", turnContext(t, g), play.DecisionContext(play.TurnAfterCall{
		Kuikae: []tile.Kind{kindOf(t, "9m")},
	}))
}

func TestChiValidation_WhenASeatOfferedPonAndChiSendsAnOfferedChi_ShouldAcceptIt(t *testing.T) {
	g := nineManDiscarded(t, [tile.SeatCount][]tile.TileID{
		copies(t, 0, "123456789s1234z"),
		slices.Concat(copies(t, 1, "99m"), copies(t, 0, "78m159p567z"), copies(t, 1, "123z")),
		slices.Concat(copies(t, 3, "9m"), copies(t, 1, "123456789s567z")),
		slices.Concat(copies(t, 2, "1234567z"), copies(t, 1, "234678p")),
	})
	chi := play.ChiAction([2]tile.TileID{tileOf(t, 0, "7m"), tileOf(t, 0, "8m")})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))
	assertEqual(t, "offers", g.LegalActions(seat(t, 1)), []play.Action{firstPon(t, g, seat(t, 1)), chi, play.PassAction()})

	_, events := script(t, g, act(seat(t, 1), chi))

	melds := testkit.CalledMelds(events)
	if len(melds) != 1 || melds[0].Meld.Kind != play.MeldChi {
		t.Errorf("melds = %+v, want one chi", melds)
	}
}

func TestCallPrompt_WhenOpenKanOutranksAnUnansweredChi_ShouldDrawTheReplacement(t *testing.T) {
	g := nineManPonAndChiSeats(t)
	caller := seat(t, 2)
	g, events := script(t, g, act(caller, play.KanAction(play.KanOpen, tileOf(t, 0, "9m"))))

	assertEqual(t, "melds", meldKinds(events), []seatMeld{{caller, play.MeldOpenKan}})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(caller))
}

func TestChiValidation_WhenTheTilesAreNotAnOfferedChi_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	build := func() game.Game { return nineManPonAndChiSeats(t) }

	for _, c := range []struct {
		pair [2]tile.TileID
		code play.RefusalCode
	}{
		{[2]tile.TileID{tileOf(t, 0, "7m"), tileOf(t, 1, "8m")}, play.CodeTileNotHeld},
		{[2]tile.TileID{tileOf(t, 0, "7m"), tileOf(t, 0, "7m")}, play.CodeTileNotHeld},
		{[2]tile.TileID{tileOf(t, 0, "6m"), tileOf(t, 0, "8m")}, play.CodeNotOffered},
	} {
		assertRefused(t, build, seat(t, 1), play.ChiAction(c.pair), refusal(play.RefusalNotOffered, c.code))
	}
}

func TestChiValidation_ShouldAcceptTheOfferedShapeInEitherTileOrder(t *testing.T) {
	g := nineManPonAndChiSeats(t)

	_, events := script(t, g,
		act(seat(t, 2), play.PassAction()),
		act(seat(t, 1), play.ChiAction([2]tile.TileID{tileOf(t, 0, "8m"), tileOf(t, 0, "7m")})),
	)

	assertEqual(t, "meld tiles", testkit.CalledMelds(events)[0].Meld.Tiles,
		[]tile.TileID{tileOf(t, 0, "7m"), tileOf(t, 0, "8m"), tileOf(t, 0, "9m")})
}

func redFiveManDiscarded(t *testing.T, fives []tile.TileID, discard tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789s1234z"),
			slices.Concat(fives, copies(t, 1, "123456789p"), copies(t, 0, "5z")),
			copies(t, 1, "123456789s1234z"),
			copies(t, 2, "123456789s1234z"),
		},
		Draws: []tile.TileID{discard},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	return g
}

func offeredPons(g game.Game, s tile.Seat) []play.Action {
	var pons []play.Action
	for _, action := range g.LegalActions(s) {
		if action.Kind() == play.ActionPon {
			pons = append(pons, action)
		}
	}
	return pons
}

func TestPon_WhenTheHandHoldsARedAndPlainFives_ShouldOfferOnePonPerLookAndTakeTheOneCalled(t *testing.T) {
	redFiveMan := id(t, 16)
	g := redFiveManDiscarded(t, ids(t, 16, 17, 18), id(t, 19))
	assertEqual(t, "pons", offeredPons(g, seat(t, 1)), []play.Action{
		play.PonAction([2]tile.TileID{redFiveMan, id(t, 17)}), play.PonAction([2]tile.TileID{id(t, 17), id(t, 18)}),
	})

	withRed, events := script(t, g, act(seat(t, 1), play.PonAction([2]tile.TileID{redFiveMan, id(t, 17)})))
	assertEqual(t, "red pon tiles", testkit.CalledMelds(events)[0].Meld.Tiles, ids(t, 16, 17, 19))
	if !slices.Contains(withRed.Hand(seat(t, 1)), id(t, 18)) {
		t.Error("the plain five left over is not in the hand")
	}

	plain, events := script(t, g, act(seat(t, 1), play.PonAction([2]tile.TileID{id(t, 18), id(t, 17)})))
	assertEqual(t, "plain pon tiles", testkit.CalledMelds(events)[0].Meld.Tiles, ids(t, 17, 18, 19))
	if !slices.Contains(plain.Hand(seat(t, 1)), redFiveMan) {
		t.Error("the red five is not in the hand")
	}

	onRed := redFiveManDiscarded(t, ids(t, 17, 18, 19), redFiveMan)
	assertEqual(t, "pons on the red five", offeredPons(onRed, seat(t, 1)),
		[]play.Action{play.PonAction([2]tile.TileID{id(t, 17), id(t, 18)})})
}

func TestPonValidation_ShouldAcceptAnyTwoHeldCopiesOfTheDiscardsKindAndRefuseTheRest(t *testing.T) {
	build := func() game.Game { return redFiveManDiscarded(t, ids(t, 16, 17, 18), id(t, 19)) }

	for _, c := range []struct {
		pair [2]tile.TileID
		code play.RefusalCode
	}{
		{[2]tile.TileID{id(t, 17), id(t, 19)}, play.CodeTileNotHeld},
		{[2]tile.TileID{id(t, 17), id(t, 17)}, play.CodeTileNotHeld},
		{[2]tile.TileID{id(t, 17), tileOf(t, 1, "1p")}, play.CodeNotOffered},
	} {
		assertRefused(t, build, seat(t, 1), play.PonAction(c.pair), refusal(play.RefusalNotOffered, c.code))
	}

	_, events := script(t, build(), act(seat(t, 1), play.PonAction([2]tile.TileID{id(t, 18), id(t, 16)})))
	assertEqual(t, "pon tiles", testkit.CalledMelds(events)[0].Meld.Tiles, ids(t, 16, 18, 19))
}

func TestMeldOffers_WhenARiichiSeatHoldsATripletOfTheDiscard_ShouldOfferNoPon(t *testing.T) {
	fivePin := copies(t, 0, "5555p")
	riichiDiscard := tileOf(t, 1, "7z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789s1234z"),
			slices.Concat(copies(t, 0, "123456m"), fivePin[:3], copies(t, 1, "7899s")),
			copies(t, 1, "123456789m1234z"),
			copies(t, 2, "123456789m1234z"),
		},
		Draws: []tile.TileID{tileOf(t, 0, "7z"), riichiDiscard, tileOf(t, 2, "7z"), tileOf(t, 3, "7z"), fivePin[3]},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(riichiDiscard)))

	g, _ = discardDrawn(t, g, 3)

	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
}

func dealerAboutToDiscardThreePin(t *testing.T) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789s1122z"),
			copies(t, 0, "123456789m3555p"),
			slices.Concat(copies(t, 1, "33p"), copies(t, 1, "1357m13579s34z")),
			slices.Concat(copies(t, 2, "123456789s"), copies(t, 2, "1234z")),
		},
		Draws: []tile.TileID{tileOf(t, 3, "3p")},
	}
	return begun(t, w, noStart())
}

func threePinDiscarded(t *testing.T) game.Game {
	t.Helper()
	g, _ := discardDrawn(t, dealerAboutToDiscardThreePin(t), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2)))
	assertEqual(t, "ron seat offers", g.LegalActions(seat(t, 1)), []play.Action{play.RonAction(), play.PassAction()})
	assertEqual(t, "pon seat offers", g.LegalActions(seat(t, 2)), []play.Action{firstPon(t, g, seat(t, 2)), play.PassAction()})
	return g
}

func TestDiscardClaim_WhenTheRonCallerPassesAndAPonIsClaimed_ShouldMakeThePon(t *testing.T) {
	g := nineManDiscarded(t, [tile.SeatCount][]tile.TileID{
		copies(t, 0, "123456789s1234z"),
		slices.Concat(copies(t, 0, "678m159p567z"), copies(t, 1, "1234z")),
		slices.Concat(copies(t, 1, "99m"), copies(t, 1, "123456789s56z")),
		copies(t, 2, "123456789p78m11z"),
	})
	assertEqual(t, "initial callers", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2), seat(t, 3)))

	g, claimed := script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))))
	assertEqual(t, "events before ron is answered", claimed, []play.Emitted(nil))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 3)))
	g, events := script(t, g, act(seat(t, 3), play.PassAction()))

	melds := testkit.CalledMelds(events)
	if len(melds) != 1 || melds[0].Seat != seat(t, 2) || melds[0].Meld.Called != play.Some(tileOf(t, 0, "9m")) {
		t.Errorf("melds = %+v, want seat 2's pon of the discard", melds)
	}
	if slices.Contains(testkit.EventKinds(events), "drew") {
		t.Error("a draw follows the pon")
	}
	assertEqual(t, "phase", g.Phase(), play.PhasePlaying)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
}

func TestDiscardClaim_WhenARiichiDiscardIsClaimedByAMeld_ShouldDepositTheRiichiFirst(t *testing.T) {
	g, _ := script(t, dealerAboutToDiscardThreePin(t), act(seat(t, 0), play.RiichiAction(tileOf(t, 3, "3p"))))

	_, events := script(t, g, act(seat(t, 1), play.PassAction()), act(seat(t, 2), firstPon(t, g, seat(t, 2))))

	kinds := slices.DeleteFunc(testkit.EventKinds(events), func(kind string) bool { return kind == "furiten_changed" })
	assertEqual(t, "kinds", kinds, []string{"riichi_deposited", "called"})
	assertEqual(t, "caller", testkit.CalledMelds(events)[0].Seat, seat(t, 2))
}

func TestDiscardClaim_WhenRonIsCalledWithOnlyAPonPending_ShouldAwardTheRon(t *testing.T) {
	g, events := script(t, threePinDiscarded(t), act(seat(t, 1), play.RonAction()))

	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
	ron, ok := roundResult(t, events).(play.Ron)
	if !ok || len(ron.Wins) != 1 || ron.Wins[0].Winner != seat(t, 1) {
		t.Errorf("result = %+v, want seat 1's ron alone", roundResult(t, events))
	}
}

func TestDiscardClaim_WhenBothCallersPass_ShouldClearThePromptAndAdvanceTheTurn(t *testing.T) {
	g, ronSeatPassed := script(t, threePinDiscarded(t), act(seat(t, 1), play.PassAction()))
	assertEqual(t, "ron seat furiten", testkit.FuritenChanges(ronSeatPassed),
		[]play.FuritenChanged{{Seat: seat(t, 1), Furiten: true}})

	g, meldSeatPassed := script(t, g, act(seat(t, 2), play.PassAction()))

	assertEqual(t, "meld seat furiten", testkit.FuritenChanges(meldSeatPassed), []play.FuritenChanged(nil))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
}

func TestResponseAction_WhenASeatSendsACallItWasNotOffered_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	riichiDiscard := tileOf(t, 1, "7z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789s1122z"),
			copies(t, 0, "123456789m1255p"),
			slices.Concat(copies(t, 1, "33p"), copies(t, 1, "1357m13579s34z")),
			slices.Concat(copies(t, 2, "123456789s"), copies(t, 2, "1234z")),
		},
		Draws: []tile.TileID{tileOf(t, 0, "7z"), riichiDiscard, tileOf(t, 2, "7z"), tileOf(t, 3, "7z"), tileOf(t, 3, "3p")},
	}
	build := func() game.Game {
		g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
		g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(riichiDiscard)))
		g, _ = discardDrawn(t, g, 3)
		return g
	}
	g := build()
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2)))
	assertEqual(t, "ron seat offers", g.LegalActions(seat(t, 1)), []play.Action{play.RonAction(), play.PassAction()})
	assertEqual(t, "pon seat offers", g.LegalActions(seat(t, 2)), []play.Action{firstPon(t, g, seat(t, 2)), play.PassAction()})

	for _, c := range []struct {
		caller tile.Seat
		action play.Action
	}{
		{seat(t, 1), play.PonAction([2]tile.TileID{tileOf(t, 0, "5p"), tileOf(t, 1, "5p")})},
		{seat(t, 2), play.ChiAction([2]tile.TileID{tileOf(t, 0, "1p"), tileOf(t, 0, "2p")})},
		{seat(t, 2), play.RonAction()},
		{seat(t, 2), play.KanAction(play.KanOpen, tileOf(t, 3, "3p"))},
	} {
		assertRefused(t, build, c.caller, c.action, notOfferedRefusal())
	}
}

func TestDiscardClaim_WhenASeatMayRonAndPonAndChoosesPon_ShouldOfferBothAndMakeItFuriten(t *testing.T) {
	threePin := tileOf(t, 2, "3p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 0, "1234567z"), copies(t, 1, "123456z")),
			slices.Concat(copies(t, 0, "123456789m35p"), copies(t, 1, "35p")),
			slices.Concat(copies(t, 0, "123456789s"), copies(t, 2, "1234z")),
			slices.Concat(copies(t, 1, "123456789s"), copies(t, 2, "1234s")),
		},
		Draws: []tile.TileID{threePin},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))
	pon := firstPon(t, g, seat(t, 1))
	assertEqual(t, "offers", g.LegalActions(seat(t, 1)), []play.Action{play.RonAction(), pon, play.PassAction()})

	g, events := script(t, g, act(seat(t, 1), pon))

	melds := testkit.CalledMelds(events)
	if len(melds) != 1 || melds[0].Seat != seat(t, 1) || melds[0].Meld.Called != play.Some(threePin) {
		t.Errorf("melds = %+v, want seat 1's pon of the discard", melds)
	}
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	assertEqual(t, "furiten", testkit.FuritenChanges(events), []play.FuritenChanged{{Seat: seat(t, 1), Furiten: true}})
}

func TestDiscardClaim_WhenASeatChoosesChiOverRonAndLosesItToAPon_ShouldBeFuritenOnItsOtherWait(t *testing.T) {
	fourPin, otherWinningOnePin := tileOf(t, 3, "4p"), tileOf(t, 1, "1p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 1, "1234567z"), copies(t, 2, "123456z")),
			slices.Concat(copies(t, 0, "123456789m235p"), copies(t, 1, "5p")),
			slices.Concat(copies(t, 1, "44p"), []tile.TileID{otherWinningOnePin}, copies(t, 0, "13579s12345z")),
			slices.Concat(copies(t, 1, "123456789m"), copies(t, 0, "2468s")),
		},
		Draws: []tile.TileID{fourPin},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	chi := play.ChiAction([2]tile.TileID{tileOf(t, 0, "2p"), tileOf(t, 0, "3p")})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2)))
	if legal := g.LegalActions(seat(t, 1)); legal[0] != play.RonAction() || !containsAction(legal, chi) {
		t.Errorf("seat 1 offers = %v, want ron first and the chi", legal)
	}
	pon := firstPon(t, g, seat(t, 2))
	assertEqual(t, "pon seat offers", g.LegalActions(seat(t, 2)), []play.Action{pon, play.PassAction()})

	g, chied := script(t, g, act(seat(t, 1), chi))
	g, ponned := script(t, g, act(seat(t, 2), pon))

	assertEqual(t, "furiten", testkit.FuritenChanges(chied), []play.FuritenChanged{{Seat: seat(t, 1), Furiten: true}})
	if melds := testkit.CalledMelds(ponned); len(melds) != 1 || melds[0].Seat != seat(t, 2) {
		t.Errorf("melds = %+v, want seat 2's pon", melds)
	}
	g, _ = script(t, g, act(seat(t, 2), play.DiscardAction(otherWinningOnePin)))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 3)))
}

func TestDiscardClaim_WhenADualSeatCallsAMeldAndAnotherSeatRons_ShouldResolveTheRon(t *testing.T) {
	oneTwoPin := [2]tile.TileID{tileOf(t, 0, "1p"), tileOf(t, 0, "2p")}
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 0, "123467z"), copies(t, 1, "123467z"), copies(t, 2, "1z")),
			slices.Concat(copies(t, 0, "123456789m125p"), copies(t, 1, "5p")),
			slices.Concat(copies(t, 0, "123456789s5z"), copies(t, 1, "12p5z")),
			slices.Concat(copies(t, 1, "123456789m"), copies(t, 1, "1234s")),
		},
		Draws: []tile.TileID{tileOf(t, 2, "3p")},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2)))
	assertEqual(t, "seat 1 offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.RonAction(), play.ChiAction(oneTwoPin), play.PassAction()})
	assertEqual(t, "seat 2 offers", g.LegalActions(seat(t, 2)), []play.Action{play.RonAction(), play.PassAction()})

	g, chied := script(t, g, act(seat(t, 1), play.ChiAction(oneTwoPin)))
	assertEqual(t, "chi events", testkit.EventKinds(chied), []string{"furiten_changed"})

	_, ronned := script(t, g, act(seat(t, 2), play.RonAction()))

	ron, ok := roundResult(t, ronned).(play.Ron)
	if !ok || len(ron.Wins) != 1 || ron.Wins[0].Winner != seat(t, 2) {
		t.Errorf("result = %+v, want seat 2's ron alone", roundResult(t, ronned))
	}
	assertEqual(t, "melds", testkit.CalledMelds(ronned), []play.Called(nil))
}

func TestDiscardClaim_WhenTheLastDiscardMayBeRonnedPonnedAndChied_ShouldOfferRonOnly(t *testing.T) {
	lastThreePin := tileOf(t, 3, "3p")
	w := testkit.StartWall{Hands: [tile.SeatCount][]tile.TileID{
		slices.Concat(copies(t, 0, "123456789m24p"), copies(t, 1, "55p")),
		slices.Concat(copies(t, 0, "3p"), copies(t, 3, "123456789s"), copies(t, 0, "567z")),
		slices.Concat(copies(t, 1, "4p"), copies(t, 3, "5p"), copies(t, 1, "1357m13579s12z")),
		slices.Concat(copies(t, 1, "33p"), copies(t, 2, "1357m13579s34z")),
	}}
	var draws []tile.TileID
	for _, free := range w.UnplacedTiles() {
		if free.Kind() != lastThreePin.Kind() && len(draws) < 69 {
			draws = append(draws, free)
		}
	}
	w.Draws = slices.Concat(draws, []tile.TileID{lastThreePin})
	g := playDefaultsWhileLiveTilesExceed(t, begun(t, w, noStart()), 0)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))

	g, _ = script(t, g, act(seat(t, 1), play.DiscardAction(lastThreePin)))

	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))
	assertEqual(t, "offers", g.LegalActions(seat(t, 0)), []play.Action{play.RonAction(), play.PassAction()})
}
