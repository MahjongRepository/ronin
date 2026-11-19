package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func nineTerminalTypes(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "192244m19p19s123z")
}

func sorted(tiles []tile.TileID) []tile.TileID {
	sortedTiles := slices.Clone(tiles)
	slices.SortFunc(sortedTiles, tile.TileID.Compare)
	return sortedTiles
}

func shown(t *testing.T, n int, tiles []tile.TileID) play.ShownHand {
	t.Helper()
	return play.ShownHand{Seat: seat(t, n), Hand: sorted(tiles)}
}

func eastStart(scores [tile.SeatCount]int, honba, riichiSticks int) play.Option[play.StartPosition] {
	return play.Some(testkit.EastStart(scores, honba, riichiSticks))
}

func TestKyuushu_WhenValid_ShouldEndTheRoundShowingTheWholeHandAndNoScoreChange(t *testing.T) {
	scores := [tile.SeatCount]int{24000, 25000, 26000, 24000}
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{nineTerminalTypes(t), junk(t, 1), junk(t, 2), junk(t, 3)},
		Draws: copies(t, 0, "6m"),
	}
	g := begun(t, w, eastStart(scores, 0, 1))

	g, events := script(t, g, act(seat(t, 0), play.KyuushuAction()))

	result := play.Abortive{Kind: play.KyuushuKyuuhai{
		Seat: seat(t, 0), Hand: slices.Concat(sorted(nineTerminalTypes(t)), copies(t, 0, "6m")),
	}}
	assertEqual[play.Event](t, "round end", events[len(events)-1].Event, play.RoundEnded{
		Result: result, Scores: scores, RiichiSticks: 1,
	})
	assertEqual(t, "score changes", result.TotalScoreChanges(), [tile.SeatCount]int{})
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
}

func TestKyuushu_WhenThePlayerHasDiscarded_ShouldBeNotOfferedAndRefused(t *testing.T) {
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{nineTerminalTypes(t), junk(t, 1), junk(t, 2), junk(t, 3)},
		Draws: slices.Concat(copies(t, 2, "6z"), copies(t, 0, "56z"), copies(t, 1, "5z"), copies(t, 0, "7z")),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 4)

	if containsAction(g.LegalActions(seat(t, 0)), play.KyuushuAction()) {
		t.Error("kyuushu is offered after a discard")
	}
	assertRefused(t, g, seat(t, 0), play.KyuushuAction(), notOfferedRefusal())
}

func TestFourWinds_WhenTheFourthSameWindDiscardDeclaresRiichi_ShouldAbortWithoutTheBet(t *testing.T) {
	var hands [tile.SeatCount][]tile.TileID
	for i := range hands {
		hands[i] = copies(t, i, "123456789m1234p")
	}
	scores := [tile.SeatCount]int{24000, 24000, 26000, 24000}
	g, _ := discardDrawn(t, begun(t, testkit.StartWall{Hands: hands, Draws: copies(t, 0, "1111z")}, eastStart(scores, 0, 2)), 3)

	_, events := script(t, g, act(seat(t, 3), play.RiichiAction(tileOf(t, 3, "1z"))))

	if discarded, ok := events[0].Event.(play.Discarded); !ok || !discarded.Riichi {
		t.Errorf("first event = %+v, want a riichi discard", events[0].Event)
	}
	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"discarded", "round_ended"})
	assertEqual[play.Event](t, "round end", events[1].Event, play.RoundEnded{
		Result: play.Abortive{Kind: play.FourWinds{}}, Scores: scores, RiichiSticks: 2,
	})
}

func tripleRonScores() [tile.SeatCount]int {
	return [tile.SeatCount]int{25000, 25000, 25000, 24000}
}

func tripleRonPrompt(t *testing.T, riichi bool) game.Game {
	t.Helper()
	discard := tileOf(t, 2, "3p")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 0, "12347z"), copies(t, 1, "1234z"), copies(t, 2, "1234z")),
			slices.Concat(copies(t, 0, "123456789m12p5z"), copies(t, 1, "5z")),
			slices.Concat(copies(t, 0, "123456789s45p6z"), copies(t, 1, "6z")),
			slices.Concat(copies(t, 1, "234567m678s345p"), copies(t, 0, "6p")),
		},
		Draws: []tile.TileID{discard},
	}
	action := play.DiscardAction(discard)
	if riichi {
		action = play.RiichiAction(discard)
	}
	g, events := script(t, begun(t, w, eastStart(tripleRonScores(), 0, 1)), act(seat(t, 0), action))
	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"discarded"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1), seat(t, 2), seat(t, 3)))
	oneTwoPin := [2]tile.TileID{tileOf(t, 0, "1p"), tileOf(t, 0, "2p")}
	assertEqual(t, "seat 1 offers", g.LegalActions(seat(t, 1)),
		[]play.Action{play.RonAction(), play.ChiAction(oneTwoPin), play.PassAction()})
	for _, n := range []int{2, 3} {
		assertEqual(t, "offers", g.LegalActions(seat(t, n)), []play.Action{play.RonAction(), play.PassAction()})
	}
	return g
}

func TestTripleRon_WhenThreeRonCallersDeclareOnARiichiDiscard_ShouldAbortShowingTheirHands(t *testing.T) {
	g, events := script(t, tripleRonPrompt(t, true),
		act(seat(t, 1), play.RonAction()), act(seat(t, 2), play.RonAction()), act(seat(t, 3), play.RonAction()))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"round_ended"})
	assertEqual[play.Event](t, "round end", events[0].Event, play.RoundEnded{
		Result: play.Abortive{Kind: play.TripleRon{
			Discarder: seat(t, 0),
			Tile:      tileOf(t, 2, "3p"),
			Hands: []play.ShownHand{
				shown(t, 1, slices.Concat(copies(t, 0, "123456789m12p5z"), copies(t, 1, "5z"))),
				shown(t, 2, slices.Concat(copies(t, 0, "123456789s45p6z"), copies(t, 1, "6z"))),
				shown(t, 3, slices.Concat(copies(t, 1, "234567m678s345p"), copies(t, 0, "6p"))),
			},
		}},
		Scores:       tripleRonScores(),
		RiichiSticks: 1,
	})
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
	assertEqual(t, "riichi seats", g.History()[0].RiichiSeats, []tile.Seat(nil))
}

func declareFourthRiichi(t *testing.T, riichiDiscard tile.TileID) (game.Game, []play.Emitted) {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 2, "123456789m"), copies(t, 0, "3344z")),
			copies(t, 0, "123456789m11p46s"),
			copies(t, 0, "234567p789s1122z"),
			copies(t, 1, "123456789m99p13s"),
		},
		Draws: slices.Concat(copies(t, 1, "5z"), copies(t, 0, "7z"), copies(t, 0, "6z"), copies(t, 0, "5z"),
			[]tile.TileID{riichiDiscard}),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	for _, riichi := range []struct {
		seat int
		tile string
	}{{1, "7z"}, {2, "6z"}, {3, "5z"}} {
		g, _ = script(t, g, act(seat(t, riichi.seat), play.RiichiAction(tileOf(t, 0, riichi.tile))))
	}
	assertEqual(t, "scores", g.Scores(), [tile.SeatCount]int{25000, 24000, 24000, 24000})
	return script(t, g, act(seat(t, 0), play.RiichiAction(riichiDiscard)))
}

func TestFourRiichi_WhenNobodyMayCallTheFourthRiichiDiscard_ShouldAbortAtOnceShowingEveryHand(t *testing.T) {
	g, events := declareFourthRiichi(t, tileOf(t, 1, "8s"))

	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"discarded", "riichi_deposited", "round_ended"})
	assertEqual[play.Event](t, "round end", events[2].Event, play.RoundEnded{
		Result: play.Abortive{Kind: play.FourRiichi{Hands: []play.ShownHand{
			shown(t, 0, slices.Concat(copies(t, 2, "123456789m"), copies(t, 0, "3344z"))),
			shown(t, 1, copies(t, 0, "123456789m11p46s")),
			shown(t, 2, copies(t, 0, "234567p789s1122z")),
			shown(t, 3, copies(t, 1, "123456789m99p13s")),
		}}},
		Scores:       [tile.SeatCount]int{24000, 24000, 24000, 24000},
		RiichiSticks: 4,
	})
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
	seats := tile.Seats()
	assertEqual(t, "riichi seats", g.History()[0].RiichiSeats, seats[:])
}

func TestFourRiichi_WhenTheRonCallerPassesTheFourthRiichiDiscard_ShouldAbortWithItsStickDeposited(t *testing.T) {
	g, _ := declareFourthRiichi(t, tileOf(t, 0, "5s"))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))

	_, passed := script(t, g, act(seat(t, 1), play.PassAction()))

	assertEqual(t, "kinds", testkit.EventKinds(passed), []string{"riichi_deposited", "round_ended"})
	assertEqual[play.Event](t, "deposit", passed[0].Event, play.RiichiDeposited{Seat: seat(t, 0), Score: 24000, RiichiSticks: 4})
	ended, _ := passed[1].Event.(play.RoundEnded)
	if abort, ok := ended.Result.(play.Abortive); !ok || ended.RiichiSticks != 4 {
		t.Errorf("round end = %+v, want a four riichi abort with 4 sticks", ended)
	} else if _, isFourRiichi := abort.Kind.(play.FourRiichi); !isFourRiichi {
		t.Errorf("abort = %+v, want four riichi", abort.Kind)
	}
}
