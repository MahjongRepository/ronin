package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func seatNotAwaitedRefusal() play.Refusal {
	return refusal(play.RefusalNotAwaited, play.CodeSeatNotAwaited)
}

func souWithWinds(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789s1234z")
}

func threePinWithTwoRonCallers(t *testing.T) game.Game {
	t.Helper()
	g, err := testkit.ThreePinWithTwoRonCallers()
	if err != nil {
		t.Fatalf("ThreePinWithTwoRonCallers error = %v", err)
	}
	return g
}

func dealerPonFromSeatThree(
	t *testing.T, dealer []tile.TileID, called, discardAfterPon tile.TileID, laterDraws []tile.TileID,
	dora play.Option[tile.TileID],
) game.Game {
	t.Helper()
	g, err := testkit.DealerPonFromSeatThree(dealer, called, discardAfterPon, laterDraws, dora)
	if err != nil {
		t.Fatalf("DealerPonFromSeatThree error = %v", err)
	}
	return g
}

func dealerPassedThreePin(t *testing.T, riichi bool) game.Game {
	t.Helper()
	chun := func(first int) tile.TileID { return tileOf(t, first, "7z") }
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m1255p"), souWithWinds(t, 1), souWithWinds(t, 2), souWithWinds(t, 3),
		},
		Draws: []tile.TileID{chun(0), tileOf(t, 0, "3p"), chun(1), chun(2), tileOf(t, 1, "3p")},
	}
	first := play.DiscardAction(chun(0))
	if riichi {
		first = play.RiichiAction(chun(0))
	}
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), first))
	g, _ = discardDrawn(t, g, 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))

	g, passed := script(t, g, act(seat(t, 0), play.PassAction()))
	assertEqual(t, "furiten", testkit.FuritenChanges(passed), []play.FuritenChanged{{Seat: seat(t, 0), Furiten: true}})
	g, _ = discardDrawn(t, g, 2)
	return g
}

func TestTsumo_WhenTemporaryOrRiichiFuriten_ShouldStillBeAllowed(t *testing.T) {
	for _, riichi := range []bool{false, true} {
		g := dealerPassedThreePin(t, riichi)
		assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
		if !containsAction(g.LegalActions(seat(t, 0)), play.TsumoAction()) {
			t.Errorf("riichi %t: tsumo is not offered", riichi)
		}

		_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

		if tsumo, ok := roundResult(t, events).(play.Tsumo); !ok || tsumo.Win.Winner != seat(t, 0) {
			t.Errorf("riichi %t: result = %+v, want seat 0's tsumo", riichi, roundResult(t, events))
		}
	}
}

func dealerTsumoOnDealtHand(t *testing.T) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m1112p"), souWithWinds(t, 1), souWithWinds(t, 2), souWithWinds(t, 3),
		},
		Draws: copies(t, 1, "2p"),
	}
	return begun(t, w, noStart())
}

func TestTsumo_WhenValid_ShouldEndTheRoundWithATsumo(t *testing.T) {
	g, events := script(t, dealerTsumoOnDealtHand(t), act(seat(t, 0), play.TsumoAction()))

	result := roundResult(t, events)
	if _, ok := result.(play.Tsumo); !ok {
		t.Errorf("result = %+v, want a tsumo", result)
	}
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
	history := g.History()
	if len(history) != 1 {
		t.Fatalf("history holds %d rounds, want 1", len(history))
	}
	assertEqual(t, "history result", history[0].Result, result)
}

func TestTsumo_WhenTheHandDoesNotWin_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "1357m2468p13579s"), souWithWinds(t, 1), souWithWinds(t, 2), souWithWinds(t, 3),
		},
		Draws: []tile.TileID{tileOf(t, 0, "7z")},
	}

	assertRefused(t, func() game.Game { return begun(t, w, noStart()) }, seat(t, 0), play.TsumoAction(), notOfferedRefusal())
}

func TestRonCallers_WhenTwoSeatsMayRon_ShouldPromptBothAndRankThemByDistanceFromTheDiscarder(t *testing.T) {
	g := threePinWithTwoRonCallers(t)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0), seat(t, 3)))
	oneTwoPin := [2]tile.TileID{tileOf(t, 1, "1p"), tileOf(t, 1, "2p")}
	for _, c := range []struct {
		caller tile.Seat
		legal  []play.Action
	}{
		{seat(t, 0), []play.Action{play.RonAction(), play.PassAction()}},
		{seat(t, 3), []play.Action{play.RonAction(), play.ChiAction(oneTwoPin), play.PassAction()}},
	} {
		decision, _ := g.Decision(c.caller)
		assertEqual(t, "decision", decision, play.Decision{
			Seat:    c.caller,
			Context: play.Call{Tile: tileOf(t, 3, "3p"), From: seat(t, 2), Source: play.SourceDiscard},
			Legal:   c.legal,
			Default: play.PassAction(),
		})
	}

	_, events := script(t, g, act(seat(t, 0), play.RonAction()), act(seat(t, 3), play.RonAction()))

	ron, _ := roundResult(t, events).(play.Ron)
	assertEqual(t, "discarder", ron.Discarder, seat(t, 2))
	var winners []tile.Seat
	for _, win := range ron.Wins {
		winners = append(winners, win.Winner)
	}
	assertEqual(t, "winners", winners, []tile.Seat{seat(t, 3), seat(t, 0)})
}

func TestRon_WhenOtherCallersArePending_ShouldRecordTheAnswerAndWait(t *testing.T) {
	g, events := script(t, threePinWithTwoRonCallers(t), act(seat(t, 3), play.RonAction()))

	assertEqual(t, "events", events, []play.Emitted(nil))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))
	if _, ok := g.Decision(seat(t, 3)); ok || len(g.LegalActions(seat(t, 3))) != 0 {
		t.Error("the seat that answered is still offered its prompt")
	}

	g, events = script(t, g, act(seat(t, 0), play.PassAction()))

	ron, ok := roundResult(t, events).(play.Ron)
	if !ok || len(ron.Wins) != 1 || ron.Wins[0].Winner != seat(t, 3) {
		t.Errorf("result = %+v, want seat 3's ron alone", roundResult(t, events))
	}
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
}

func TestAnswerCall_WhenTheSameSeatAnswersTwice_ShouldBeNotAwaitedAndChangeNothing(t *testing.T) {
	build := func() game.Game {
		g, _ := script(t, threePinWithTwoRonCallers(t), act(seat(t, 3), play.PassAction()))
		return g
	}

	for _, action := range []play.Action{play.RonAction(), play.PassAction()} {
		assertRefused(t, build, seat(t, 3), action, refusal(play.RefusalNotAwaited, play.CodeAlreadyAnswered))
	}
}

func TestTurnAction_WhenAPromptIsPending_ShouldBeNotAwaitedAndChangeNothing(t *testing.T) {
	build := func() game.Game { return threePinWithTwoRonCallers(t) }
	g := build()
	own := g.Hand(seat(t, 2))[0]

	for _, c := range []struct {
		caller tile.Seat
		action play.Action
	}{
		{seat(t, 2), play.DiscardAction(own)},
		{seat(t, 2), play.RiichiAction(own)},
		{seat(t, 2), play.TsumoAction()},
		{seat(t, 2), play.KyuushuAction()},
		{seat(t, 2), play.KanAction(play.KanClosed, own)},
		{seat(t, 2), play.KanAction(play.KanAdded, own)},
		{seat(t, 0), play.DiscardAction(g.Hand(seat(t, 0))[0])},
	} {
		assertRefused(t, build, c.caller, c.action, seatNotAwaitedRefusal())
	}
}

func TestCallAnswer_WhenTheSeatHasNoPrompt_ShouldBeNotAwaitedAndChangeNothing(t *testing.T) {
	prompted := func() game.Game { return threePinWithTwoRonCallers(t) }
	turn := func() game.Game { return dealerTsumoOnDealtHand(t) }

	pon := play.PonAction([2]tile.TileID{tileOf(t, 0, "3p"), tileOf(t, 1, "3p")})
	for _, action := range []play.Action{play.RonAction(), play.PassAction(), pon} {
		assertRefused(t, turn, seat(t, 0), action, seatNotAwaitedRefusal())
		assertRefused(t, prompted, seat(t, 1), action, seatNotAwaitedRefusal())
	}
}

func TestRon_WhenValid_ShouldEndTheRoundWithARon(t *testing.T) {
	_, events := script(t, threePinWithTwoRonCallers(t),
		act(seat(t, 0), play.RonAction()), act(seat(t, 3), play.PassAction()))

	ron, ok := roundResult(t, events).(play.Ron)
	if !ok || len(ron.Wins) != 1 || ron.Wins[0].Winner != seat(t, 0) {
		t.Errorf("result = %+v, want seat 0's ron alone", roundResult(t, events))
	}
	if _, ok := events[len(events)-1].Event.(play.RoundEnded); !ok {
		t.Errorf("last event = %+v, want RoundEnded", events[len(events)-1].Event)
	}
}

func dealerWithEightSouPon(t *testing.T, closed, laterDraws []tile.TileID) game.Game {
	t.Helper()
	extraChun := tileOf(t, 0, "7z")
	dealer := slices.Concat(copies(t, 0, "88s"), closed, []tile.TileID{extraChun})
	draws := slices.Concat(copies(t, 0, "666z"), laterDraws)
	g := dealerPonFromSeatThree(t, dealer, tileOf(t, 2, "8s"), extraChun, draws, play.Option[tile.TileID]{})
	g, _ = discardDrawn(t, g, 3)
	return g
}

func TestTsumo_WhenAnOpenPonAndTheDrawnHandComplete_ShouldWin(t *testing.T) {
	g := dealerWithEightSouPon(t, copies(t, 0, "234567m2345s"), copies(t, 1, "5s"))
	if !containsAction(g.LegalActions(seat(t, 0)), play.TsumoAction()) {
		t.Fatal("tsumo is not offered")
	}

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	tsumo, _ := roundResult(t, events).(play.Tsumo)
	if len(tsumo.Win.Melds) != 1 {
		t.Fatalf("melds = %+v, want one", tsumo.Win.Melds)
	}
	assertEqual(t, "pon tiles", tsumo.Win.Melds[0].Tiles, slices.Concat(copies(t, 0, "88s"), copies(t, 2, "8s")))
	assertEqual(t, "hand", tsumo.Win.Hand, copies(t, 0, "234567m2345s"))
}

func TestWaits_WhenTheHandHasAnOpenPon_ShouldMakeADiscardedWaitFuriten(t *testing.T) {
	for _, c := range []struct {
		drawn  tile.TileID
		isWait bool
	}{
		{tileOf(t, 0, "1s"), true},
		{tileOf(t, 0, "4s"), true},
		{tileOf(t, 1, "9m"), false},
	} {
		g := dealerWithEightSouPon(t, copies(t, 0, "234567m2355s"), []tile.TileID{c.drawn})

		_, discarded := script(t, g, act(seat(t, 0), play.DiscardAction(c.drawn)))

		var want []play.FuritenChanged
		if c.isWait {
			want = []play.FuritenChanged{{Seat: seat(t, 0), Furiten: true}}
		}
		assertEqual(t, "furiten", testkit.FuritenChanges(discarded), want)
	}
}

func TestFuriten_WhenAWaitWasDiscardedTurnsAgoAndClaimed_ShouldBlockTheRon(t *testing.T) {
	claimedThreePin, sixPin := tileOf(t, 0, "3p"), tileOf(t, 0, "6p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m345p9s"),
			slices.Concat(copies(t, 1, "33p"), copies(t, 1, "123456789m"), copies(t, 3, "17z")),
			slices.Concat(copies(t, 2, "123456789s"), copies(t, 2, "1234z")),
			slices.Concat(copies(t, 3, "123456789s"), copies(t, 3, "2345z")),
		},
		Draws: []tile.TileID{tileOf(t, 1, "9s"), sixPin},
	}
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), play.DiscardAction(claimedThreePin)))
	g, _ = script(t, g, act(seat(t, 1), firstPon(t, g, seat(t, 1))), act(seat(t, 1), play.DiscardAction(tileOf(t, 3, "7z"))))

	g, discarded := script(t, g, act(seat(t, 2), play.DiscardAction(sixPin)))

	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 3)))
	if slices.Contains(testkit.EventKinds(discarded), "round_ended") {
		t.Error("the round ended on the furiten wait")
	}
}

func dealerWithOneManPon(t *testing.T, closed, laterDraws []tile.TileID) game.Game {
	t.Helper()
	extraChun := tileOf(t, 0, "7z")
	dealer := slices.Concat(copies(t, 1, "11m"), closed, []tile.TileID{extraChun})
	fiveManDoraIndicator := tileOf(t, 3, "4m")
	return dealerPonFromSeatThree(t, dealer, tileOf(t, 0, "1m"), extraChun, laterDraws, play.Some(fiveManDoraIndicator))
}

func TestShibari_WhenAnOpenHandHasOnlyDora_ShouldRejectTheTsumo(t *testing.T) {
	build := func() game.Game {
		g := dealerWithOneManPon(t, copies(t, 0, "2345m234p567s"),
			slices.Concat(copies(t, 0, "666z"), []tile.TileID{tileOf(t, 1, "5m")}))
		g, _ = discardDrawn(t, g, 3)
		return g
	}
	g := build()
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))

	if containsAction(g.LegalActions(seat(t, 0)), play.TsumoAction()) {
		t.Error("tsumo is offered on a yakuless hand")
	}
	assertRefused(t, build, seat(t, 0), play.TsumoAction(), notOfferedRefusal())
}

func TestShibari_WhenAnOpenHandHasOnlyDora_ShouldRejectTheRon(t *testing.T) {
	g := dealerWithOneManPon(t, copies(t, 0, "2345m234p567s"),
		slices.Concat(copies(t, 0, "66z"), []tile.TileID{tileOf(t, 1, "5m")}))
	g, _ = discardDrawn(t, g, 2)

	g, discarded := discardDrawn(t, g, 1)

	if containsAction(g.LegalActions(seat(t, 0)), play.RonAction()) {
		t.Error("ron is offered on a yakuless hand")
	}
	assertEqual(t, "furiten", testkit.FuritenChanges(discarded), []play.FuritenChanged{{Seat: seat(t, 0), Furiten: true}})
}

func manWithWinds(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "23456789m12345z")
}

func souWithHonors(t *testing.T, first, honorsFirst int) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, first, "123456789s"), copies(t, honorsFirst, "2347z"))
}

func TestTenhou_WhenAClosedKanWasMade_ShouldNotBeScored(t *testing.T) {
	oneMan := copies(t, 0, "1111m")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(oneMan, copies(t, 0, "234567789p")), manWithWinds(t, 1), manWithWinds(t, 2), manWithWinds(t, 3),
		},
		Draws:   copies(t, 0, "5s"),
		Rinshan: copies(t, 1, "5s"),
	}
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), play.KanAction(play.KanClosed, oneMan[0])))

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	win := firstWin(t, events)
	if !slices.Contains(win.Yaku, play.YakuRinshan) || slices.Contains(win.Yaku, play.YakuTenhou) {
		t.Errorf("yaku = %v, want rinshan and no tenhou", win.Yaku)
	}
}

func TestChiihou_WhenTheDealerMadeAClosedKan_ShouldNotBeScored(t *testing.T) {
	east := copies(t, 0, "1111z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(east, copies(t, 1, "123456789s")),
			copies(t, 0, "123456789m1255p"),
			souWithHonors(t, 2, 0),
			souWithHonors(t, 3, 1),
		},
		Draws:   slices.Concat([]tile.TileID{tileOf(t, 0, "5z")}, copies(t, 0, "3p")),
		Rinshan: []tile.TileID{tileOf(t, 0, "6z")},
	}
	g, _ := script(t, begun(t, w, noStart()),
		act(seat(t, 0), play.KanAction(play.KanClosed, east[0])),
		act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "5z"))),
	)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))

	_, events := script(t, g, act(seat(t, 1), play.TsumoAction()))

	assertEqual(t, "yaku", firstWin(t, events).Yaku, []play.YakuID{play.YakuTsumo, play.YakuIttsu})
}

func TestRon_WhenOnTheFirstTurnAfterAClosedKan_ShouldScoreNoFirstTurnYaku(t *testing.T) {
	east := copies(t, 0, "1111z")
	threePin := tileOf(t, 0, "3p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(east, copies(t, 1, "123456789s")),
			copies(t, 0, "123456789m1255p"),
			souWithHonors(t, 2, 0),
			souWithHonors(t, 3, 1),
		},
		Draws:   []tile.TileID{tileOf(t, 0, "5z")},
		Rinshan: []tile.TileID{threePin},
	}
	g, _ := script(t, begun(t, w, noStart()),
		act(seat(t, 0), play.KanAction(play.KanClosed, east[0])),
		act(seat(t, 0), play.DiscardAction(threePin)),
	)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))

	_, events := script(t, g, act(seat(t, 1), play.RonAction()))

	assertEqual(t, "yaku", firstWin(t, events).Yaku, []play.YakuID{play.YakuIttsu})
}
