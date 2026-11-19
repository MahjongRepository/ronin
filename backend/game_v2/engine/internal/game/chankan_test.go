package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func threePin(t *testing.T, first int) tile.TileID {
	t.Helper()
	return tileOf(t, first, "3p")
}

func hatsu(t *testing.T, first int) tile.TileID {
	t.Helper()
	return tileOf(t, first, "6z")
}

func chankanBystander(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789s1234z")
}

func seatTwoDiscardAfterPon(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 0, "7z")
}

func penchanOnThreePin(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "123456789m1255p")
}

func otherPenchanOnThreePin(t *testing.T) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 1, "123456789m12p"), copies(t, 2, "55p"))
}

func kanAfterOneGoAround(t *testing.T) []tile.TileID {
	t.Helper()
	return []tile.TileID{hatsu(t, 1), hatsu(t, 2), hatsu(t, 3), threePin(t, 3)}
}

func threePinWall(t *testing.T, seatZero, seatThree, laterDraws []tile.TileID) testkit.StartWall {
	t.Helper()
	seatTwo := slices.Concat(copies(t, 1, "33p"), copies(t, 1, "123456789s"),
		[]tile.TileID{tileOf(t, 0, "5z"), seatTwoDiscardAfterPon(t)})
	return testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{seatZero, chankanBystander(t, 0), seatTwo, seatThree},
		Draws: slices.Concat([]tile.TileID{hatsu(t, 0), threePin(t, 0)}, laterDraws),
		Dora:  play.Some(tileOf(t, 3, "5z")),
	}
}

func threePinPonnedBySeatTwo(t *testing.T, w testkit.StartWall, seatZeroOpening func(tile.TileID) play.Action) game.Game {
	t.Helper()
	g := begun(t, w, noStart())
	drawn, _ := testkit.Drawn(g)
	g, _ = script(t, g, act(seat(t, 0), seatZeroOpening(drawn)))
	g, _ = discardDrawn(t, g, 1)

	pending := awaitedSeats(g)
	if !slices.Contains(pending, seat(t, 2)) {
		t.Fatalf("awaited seats = %v, want seat 2 among them", pending)
	}
	for _, other := range pending {
		if other != seat(t, 2) {
			g, _ = script(t, g, act(other, play.PassAction()))
		}
	}
	g, _ = script(t, g,
		act(seat(t, 2), firstPon(t, g, seat(t, 2))),
		act(seat(t, 2), play.DiscardAction(seatTwoDiscardAfterPon(t))),
	)
	return g
}

func addedThreePinKan(t *testing.T, g game.Game) (game.Game, []play.Emitted) {
	t.Helper()
	assertEqual(t, "awaiting before the kan", g.Awaiting(), awaitingTurn(seat(t, 2)))
	return script(t, g, act(seat(t, 2), play.KanAction(play.KanAdded, threePin(t, 3))))
}

func kanAfterGoAround(t *testing.T, seatZero, seatThree []tile.TileID) (game.Game, []play.Emitted) {
	t.Helper()
	w := threePinWall(t, seatZero, seatThree, kanAfterOneGoAround(t))
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 3)
	return addedThreePinKan(t, g)
}

func threePinAddedKan(t *testing.T) play.Called {
	t.Helper()
	return play.Called{Seat: seat(t, 2), Meld: play.MeldView{
		Kind:   play.MeldAddedKan,
		Tiles:  []tile.TileID{threePin(t, 0), threePin(t, 1), threePin(t, 2), threePin(t, 3)},
		Called: play.Some(threePin(t, 0)),
		From:   play.Some(seat(t, 1)),
	}}
}

func assertKanStoodUnrobbed(t *testing.T, g game.Game, events []play.Emitted) {
	t.Helper()
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{threePinAddedKan(t)})
}

func assertOwnership(t *testing.T, g game.Game) {
	t.Helper()
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}
}

func ronResult(t *testing.T, events []play.Emitted) play.Ron {
	t.Helper()
	ron, ok := roundResult(t, events).(play.Ron)
	if !ok {
		t.Fatalf("result = %+v, want a ron", roundResult(t, events))
	}
	return ron
}

func TestChankan_WhenNoSeatWaitsOnTheTile_ShouldNotBePossible(t *testing.T) {
	waitingOnFourAndSevenPin := copies(t, 0, "123456789m5677p")

	g, events := kanAfterGoAround(t, waitingOnFourAndSevenPin, chankanBystander(t, 3))

	assertKanStoodUnrobbed(t, g, events)
}

func TestChankan_WhenTheWaitingSeatIsInDiscardFuriten_ShouldNotBePossible(t *testing.T) {
	furitenOnSixPin := copies(t, 0, "123456789m4555p")
	later := []tile.TileID{hatsu(t, 1), tileOf(t, 0, "6p"), hatsu(t, 3), threePin(t, 3)}
	w := threePinWall(t, furitenOnSixPin, chankanBystander(t, 3), later)
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 3)

	g, events := addedThreePinKan(t, g)

	assertKanStoodUnrobbed(t, g, events)
}

func TestChankan_WhenTwoSeatsWait_ShouldPromptBothAndListTheWinsInHeadBumpOrder(t *testing.T) {
	g, events := kanAfterGoAround(t, penchanOnThreePin(t), otherPenchanOnThreePin(t))
	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{threePinAddedKan(t)})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0), seat(t, 3)))

	_, events = script(t, g, act(seat(t, 0), play.RonAction()), act(seat(t, 3), play.RonAction()))

	ron := ronResult(t, events)
	assertEqual(t, "discarder", ron.Discarder, seat(t, 2))
	assertEqual(t, "winners", winners(ron), []tile.Seat{seat(t, 3), seat(t, 0)})
	for _, win := range ron.Wins {
		assertEqual(t, "win tile", win.WinTile, threePin(t, 3))
		if !slices.Contains(win.Yaku, play.YakuChankan) {
			t.Errorf("seat %d's yaku = %v, want chankan", win.Winner.Index(), win.Yaku)
		}
	}
}

func TestChankan_WhenTheWaitingSeatIsInRiichiFuriten_ShouldNotBePossible(t *testing.T) {
	w := threePinWall(t, penchanOnThreePin(t), chankanBystander(t, 3), kanAfterOneGoAround(t))
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.RiichiAction), 3)

	g, events := addedThreePinKan(t, g)

	assertKanStoodUnrobbed(t, g, events)
}

func TestChankan_WhenTheWaitingSeatIsInTemporaryFuriten_ShouldNotBePossible(t *testing.T) {
	temporaryFuritenOnThreeAndSixPin := slices.Concat(copies(t, 1, "123456789m"), copies(t, 0, "4555p"))
	later := []tile.TileID{hatsu(t, 1), hatsu(t, 2), tileOf(t, 0, "6p"), threePin(t, 3)}
	w := threePinWall(t, chankanBystander(t, 2), temporaryFuritenOnThreeAndSixPin, later)
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 3)))
	g, _ = script(t, g, act(seat(t, 3), play.PassAction()))

	g, events := addedThreePinKan(t, g)

	assertKanStoodUnrobbed(t, g, events)
}

func TestAddedKan_WhenASeatMayRobIt_ShouldPromptTheChankan(t *testing.T) {
	g, events := kanAfterGoAround(t, chankanBystander(t, 2), otherPenchanOnThreePin(t))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called"})
	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{threePinAddedKan(t)})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 3)))
	decision, _ := g.Decision(seat(t, 3))
	assertEqual(t, "decision", decision, play.Decision{
		Seat:    seat(t, 3),
		Context: play.Call{Tile: threePin(t, 3), From: seat(t, 2), Source: play.SourceAddedKan},
		Legal:   []play.Action{play.RonAction(), play.PassAction()},
		Default: play.PassAction(),
	})
}

func TestChankan_WhenARiichiSeatRobsTheAddedKanWithinIppatsu_ShouldKeepIppatsu(t *testing.T) {
	w := threePinWall(t, penchanOnThreePin(t), chankanBystander(t, 3), kanAfterOneGoAround(t))
	w.Ura = []tile.TileID{tileOf(t, 2, "5z")}
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 1)
	g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(hatsu(t, 2))))
	g, _ = discardDrawn(t, g, 1)
	g, declared := addedThreePinKan(t, g)

	_, events := script(t, g, act(seat(t, 0), play.RonAction()))

	assertEqual(t, "yaku", firstWin(t, events).Yaku,
		[]play.YakuID{play.YakuRiichi, play.YakuIppatsu, play.YakuChankan, play.YakuIttsu})
	assertEqual(t, "dora", testkit.DoraReveals(slices.Concat(declared, events)), []tile.TileID(nil))
}

func TestChankan_WhenTheRobbedAddedKanFollowsAnOpenKanWithItsDoraPending_ShouldRevealNothing(t *testing.T) {
	ninePin := copies(t, 0, "9999p")
	w := threePinWall(t, chankanBystander(t, 2), otherPenchanOnThreePin(t), ninePin[:1])
	w.Hands[2] = slices.Concat(copies(t, 1, "33p"), ninePin[1:], copies(t, 1, "1234567s"),
		[]tile.TileID{seatTwoDiscardAfterPon(t)})
	w.Rinshan = []tile.TileID{threePin(t, 3)}
	w.KanDora = []tile.TileID{tileOf(t, 0, "4p")}
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 1)
	g, openKan := script(t, g, act(seat(t, 2), play.KanAction(play.KanOpen, ninePin[0])))
	assertEqual(t, "open kan dora", testkit.DoraReveals(openKan), []tile.TileID(nil))

	g, robbed := addedThreePinKan(t, g)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 3)))
	_, events := script(t, g, act(seat(t, 3), play.RonAction()))

	assertEqual(t, "dora", testkit.DoraReveals(slices.Concat(robbed, events)), []tile.TileID(nil))
	win := firstWin(t, events)
	assertEqual(t, "winner and loser", [2]any{win.Winner, win.Loser}, [2]any{seat(t, 3), play.Some(seat(t, 2))})
	if !slices.Contains(win.Yaku, play.YakuChankan) {
		t.Errorf("yaku = %v, want chankan", win.Yaku)
	}
	assertEqual(t, "dora count", win.Dora.Dora, 0)
}

func TestHandValue_WhenARiichiSeatRobsAnAddedKan_ShouldIncludeChankanAndCountTheDora(t *testing.T) {
	later := slices.Concat(kanAfterOneGoAround(t)[:3], copies(t, 1, "7z"), copies(t, 2, "7z"), copies(t, 3, "7z"),
		copies(t, 1, "4z"), []tile.TileID{threePin(t, 3)})
	w := threePinWall(t, penchanOnThreePin(t), chankanBystander(t, 3), later)
	w.Dora = play.Some(tileOf(t, 1, "1m"))
	w.Ura = []tile.TileID{tileOf(t, 2, "5z")}
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 1)
	g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(hatsu(t, 2))))
	g, _ = discardDrawn(t, g, 5)
	g, _ = addedThreePinKan(t, g)

	_, events := script(t, g, act(seat(t, 0), play.RonAction()))

	win := firstWin(t, events)
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuRiichi, play.YakuChankan, play.YakuIttsu})
	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 1, AkaDora: 2})
	assertEqual(t, "ura indicators", win.UraIndicators, []tile.TileID{tileOf(t, 2, "5z")})
}

func fourMan(t *testing.T, first int) tile.TileID {
	t.Helper()
	return tileOf(t, first, "4m")
}

func openYakulessWaitRobsFourManAddedKan(t *testing.T) (game.Game, []tile.Seat) {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 1, "123456789p"), copies(t, 0, "1234z")),
			slices.Concat(copies(t, 1, "11m"), copies(t, 0, "23m456p67899s"), copies(t, 1, "7z")),
			slices.Concat(copies(t, 1, "44m"), copies(t, 2, "123456789p"), copies(t, 0, "5z"),
				[]tile.TileID{seatTwoDiscardAfterPon(t)}),
			slices.Concat(copies(t, 3, "123456789p"), copies(t, 1, "1234z")),
		},
		Draws: []tile.TileID{
			tileOf(t, 0, "1m"), hatsu(t, 0), fourMan(t, 0), hatsu(t, 1), hatsu(t, 2), hatsu(t, 3), fourMan(t, 3),
		},
		Dora: play.Some(tileOf(t, 3, "5z")),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	g, _ = script(t, g, act(seat(t, 1), firstPon(t, g, seat(t, 1))), act(seat(t, 1), play.DiscardAction(tileOf(t, 1, "7z"))))
	g, _ = discardDrawn(t, g, 2)
	fourManCallers := awaitedSeats(g)
	g, _ = script(t, g,
		act(seat(t, 2), firstPon(t, g, seat(t, 2))),
		act(seat(t, 2), play.DiscardAction(seatTwoDiscardAfterPon(t))),
	)
	g, _ = discardDrawn(t, g, 3)
	g, _ = script(t, g, act(seat(t, 2), play.KanAction(play.KanAdded, fourMan(t, 3))))
	return g, fourManCallers
}

func TestChankan_WhenAnOpenHandHasNoYakuButChankan_ShouldBePossible(t *testing.T) {
	g, _ := openYakulessWaitRobsFourManAddedKan(t)

	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))
	assertEqual(t, "offers", g.LegalActions(seat(t, 1)), []play.Action{play.RonAction(), play.PassAction()})
}

func TestHandValue_WhenAnOpenHandHasNoYakuButChankan_ShouldScoreWithChankanAlone(t *testing.T) {
	g, fourManCallers := openYakulessWaitRobsFourManAddedKan(t)
	assertEqual(t, "four man callers", fourManCallers, []tile.Seat{seat(t, 2)})

	_, events := script(t, g, act(seat(t, 1), play.RonAction()))

	win := firstWin(t, events)
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuChankan})
	assertEqual(t, "dora", win.Dora, play.DoraCount{AkaDora: 1})
}

func kokushiOnOneMan(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "99m19p19s1234567z")
}

func oneManClosedKan(t *testing.T) play.Called {
	t.Helper()
	return play.Called{Seat: seat(t, 0), Meld: play.MeldView{Kind: play.MeldClosedKan, Tiles: copies(t, 0, "1111m")}}
}

func oneManQuadAfterDraw(t *testing.T, seatOne []tile.TileID, kanDora tile.TileID) game.Game {
	t.Helper()
	oneMan := copies(t, 0, "1111m")
	dealer := slices.Concat(oneMan[:3], copies(t, 1, "123456789p"), copies(t, 1, "2s"))
	w := testkit.StartWall{
		Hands:   [tile.SeatCount][]tile.TileID{dealer, seatOne, filler(t, 2), filler(t, 3)},
		Draws:   oneMan[3:],
		KanDora: []tile.TileID{kanDora},
	}
	return begun(t, w, noStart())
}

func closedOneManKan(t *testing.T) testkit.SeatAction {
	t.Helper()
	return act(seat(t, 0), play.KanAction(play.KanClosed, tileOf(t, 0, "1m")))
}

func TestKokushiChankan_WhenKokushiWaitsOnTheClosedKanTile_ShouldPromptTheRobbery(t *testing.T) {
	g, events := script(t, oneManQuadAfterDraw(t, kokushiOnOneMan(t), tileOf(t, 0, "7s")), closedOneManKan(t))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called"})
	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{oneManClosedKan(t)})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))
	decision, _ := g.Decision(seat(t, 1))
	assertEqual(t, "context", decision.Context, play.DecisionContext(play.Call{
		Tile: tileOf(t, 0, "1m"), From: seat(t, 0), Source: play.SourceClosedKan,
	}))
	assertEqual(t, "offers", decision.Legal, []play.Action{play.RonAction(), play.PassAction()})
}

func TestKokushiChankan_WhenTheTenpaiHandIsNotKokushi_ShouldNotRobTheClosedKan(t *testing.T) {
	dealer := slices.Concat(copies(t, 0, "111m"), copies(t, 1, "123456789s"), copies(t, 0, "1z"))
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			dealer,
			copies(t, 0, "23456789m12355p"),
			slices.Concat(copies(t, 2, "123456789p"), copies(t, 0, "2345z")),
			slices.Concat(copies(t, 3, "123456789p"), copies(t, 1, "2345z")),
		},
		Draws: copies(t, 3, "1m"),
	}

	g, events := script(t, begun(t, w, noStart()), closedOneManKan(t))

	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	called := testkit.CalledMelds(events)
	if len(called) != 1 || called[0].Seat != seat(t, 0) || called[0].Meld.Kind != play.MeldClosedKan {
		t.Errorf("called = %+v, want seat 0's closed kan", called)
	}
}

func TestClosedKan_WhenKokushiMayRobItAndDeclines_ShouldCompleteTheKan(t *testing.T) {
	kanDora := tileOf(t, 0, "7s")
	g, prompted := script(t, oneManQuadAfterDraw(t, kokushiOnOneMan(t), kanDora), closedOneManKan(t))
	assertEqual(t, "melds", testkit.CalledMelds(prompted), []play.Called{oneManClosedKan(t)})
	assertEqual(t, "prompted dora", testkit.DoraReveals(prompted), []tile.TileID(nil))

	g, declined := script(t, g, act(seat(t, 1), play.PassAction()))

	assertEqual(t, "kinds", testkit.EventKinds(declined),
		[]string{"dora_revealed", "drew", "drew", "drew", "drew", "furiten_changed"})
	assertEqual(t, "dora", testkit.DoraReveals(declined), []tile.TileID{kanDora})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	assertOwnership(t, g)
}

func TestChankan_WhenTheAddedKanIsRobbed_ShouldAnnounceTheKanThenEndTheRoundWithNoDora(t *testing.T) {
	g, declared := kanAfterGoAround(t, chankanBystander(t, 2), otherPenchanOnThreePin(t))
	assertEqual(t, "declared kinds", testkit.EventKinds(declared), []string{"called"})
	assertEqual(t, "declared", testkit.CalledMelds(declared), []play.Called{threePinAddedKan(t)})
	assertOwnership(t, g)

	g, robbed := script(t, g, act(seat(t, 3), play.RonAction()))

	assertEqual(t, "kinds", testkit.EventKinds(robbed), []string{"round_ended"})
	ron := ronResult(t, robbed)
	assertEqual(t, "discarder", ron.Discarder, seat(t, 2))
	assertEqual(t, "winners", winners(ron), []tile.Seat{seat(t, 3)})
	assertEqual(t, "win tile", ron.Wins[0].WinTile, threePin(t, 3))
	if !slices.Contains(ron.Wins[0].Yaku, play.YakuChankan) {
		t.Errorf("yaku = %v, want chankan", ron.Wins[0].Yaku)
	}
	assertOwnership(t, g)
}

func TestChankan_WhenEveryRobberPasses_ShouldLetTheAddedKanStandWithItsRinshanDrawAndDoraAtTheNextDiscard(t *testing.T) {
	g, declared := kanAfterGoAround(t, chankanBystander(t, 2), otherPenchanOnThreePin(t))
	assertEqual(t, "declared", testkit.CalledMelds(declared), []play.Called{threePinAddedKan(t)})

	g, passed := script(t, g, act(seat(t, 3), play.PassAction()))

	assertEqual(t, "melds", testkit.CalledMelds(passed), []play.Called(nil))
	assertEqual(t, "dora", testkit.DoraReveals(passed), []tile.TileID(nil))
	assertEqual(t, "kinds", testkit.EventKinds(passed)[:4], []string{"drew", "drew", "drew", "drew"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	assertOwnership(t, g)

	_, discarded := discardDrawn(t, g, 1)

	assertEqual(t, "discard kinds", testkit.EventKinds(discarded)[:2], []string{"discarded", "dora_revealed"})
	assertEqual(t, "dora count", len(testkit.DoraReveals(discarded)), 1)
}

func TestKokushiChankan_WhenTheClosedKanIsRobbed_ShouldAnnounceTheKanThenEndTheRoundWithNoDora(t *testing.T) {
	oneMan := copies(t, 0, "1111m")
	g, declared := script(t, oneManQuadAfterDraw(t, kokushiOnOneMan(t), tileOf(t, 0, "7s")), closedOneManKan(t))
	assertEqual(t, "melds", testkit.CalledMelds(declared), []play.Called{oneManClosedKan(t)})
	assertEqual(t, "dora", testkit.DoraReveals(declared), []tile.TileID(nil))
	assertOwnership(t, g)

	g, robbed := script(t, g, act(seat(t, 1), play.RonAction()))

	assertEqual(t, "kinds", testkit.EventKinds(robbed), []string{"round_ended", "game_ended"})
	win := firstWin(t, robbed)
	assertEqual(t, "win", [3]any{win.Winner, win.Loser, win.WinTile}, [3]any{seat(t, 1), play.Some(seat(t, 0)), oneMan[0]})
	if !slices.Contains(win.Yaku, play.YakuKokushiMusou) {
		t.Errorf("yaku = %v, want kokushi musou", win.Yaku)
	}
	assertOwnership(t, g)
}

func TestChankanPrompt_WhenTheDeclarerWaitsOnItsOwnDiscard_ShouldAnnounceOnlyTheKan(t *testing.T) {
	later := slices.Concat(kanAfterOneGoAround(t)[:3], copies(t, 1, "7z"))
	w := threePinWall(t, chankanBystander(t, 2), otherPenchanOnThreePin(t), later)
	w.Hands[2] = slices.Concat(copies(t, 1, "333p"), copies(t, 1, "123456789s"), []tile.TileID{seatTwoDiscardAfterPon(t)})
	g, _ := discardDrawn(t, threePinPonnedBySeatTwo(t, w, play.DiscardAction), 3)

	g, declared := addedThreePinKan(t, g)

	assertEqual(t, "kinds", testkit.EventKinds(declared), []string{"called"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 3)))
}
