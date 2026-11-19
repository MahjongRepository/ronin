package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func assertBranchesStayApart(t *testing.T, build func() game.Game, first, second []testkit.SeatAction) {
	t.Helper()
	base := build()

	firstBranch, _ := script(t, base, first...)
	secondBranch, _ := script(t, base, second...)

	assertSameGame(t, base, build())
	wantFirst, _ := script(t, build(), first...)
	assertSameGame(t, firstBranch, wantFirst)
	wantSecond, _ := script(t, build(), second...)
	assertSameGame(t, secondBranch, wantSecond)
}

func TestAct_WhenTwoDiscardsBranchFromOneState_ShouldLeaveTheStateAndEachBranchApart(t *testing.T) {
	build := func() game.Game {
		return playDefaultsWhileLiveTilesExceed(t, begun(t, notenWall(t), noStart()), 57)
	}
	turn, _ := testkit.TurnSeat(build())
	drawn, _ := testkit.Drawn(build())
	held := build().Hand(turn)[0]

	assertBranchesStayApart(t, build,
		[]testkit.SeatAction{act(turn, play.DiscardAction(drawn))},
		[]testkit.SeatAction{act(turn, play.DiscardAction(held))},
	)
}

func TestAct_WhenTwoCallAnswersBranchFromOneState_ShouldLeaveTheStateAndEachBranchApart(t *testing.T) {
	build := func() game.Game { return threePinDiscarded(t) }

	assertBranchesStayApart(t, build,
		[]testkit.SeatAction{act(seat(t, 1), play.PassAction()), act(seat(t, 2), play.PassAction())},
		[]testkit.SeatAction{act(seat(t, 1), play.RonAction()), act(seat(t, 2), play.PassAction())},
	)
}

func TestAct_WhenAnAddedKanAndADiscardBranchFromOneState_ShouldLeaveTheStateAndEachBranchApart(t *testing.T) {
	build := func() game.Game {
		g, _ := onePonAndFourthCopy(t)
		g, _ = discardDrawn(t, g, 3)
		return g
	}
	_, oneMan := onePonAndFourthCopy(t)

	assertBranchesStayApart(t, build,
		[]testkit.SeatAction{act(seat(t, 0), play.KanAction(play.KanAdded, oneMan[3]))},
		[]testkit.SeatAction{act(seat(t, 0), play.DiscardAction(oneMan[3]))},
	)
}

func TestAct_WhenARiichiAndAPlainDiscardBranchFromOneState_ShouldLeaveTheStateAndEachBranchApart(t *testing.T) {
	build := func() game.Game {
		draws := []tile.TileID{tileOf(t, 0, "7z"), tileOf(t, 0, "5z"), tileOf(t, 0, "6z"), tileOf(t, 1, "7z"), tileOf(t, 1, "5z")}
		g, _ := discardDrawn(t, dealerAfterDraw(t, copies(t, 0, "1123456788899m"), draws), tile.SeatCount)
		return g
	}

	assertBranchesStayApart(t, build,
		[]testkit.SeatAction{act(seat(t, 0), play.RiichiAction(tileOf(t, 1, "5z")))},
		[]testkit.SeatAction{act(seat(t, 0), play.DiscardAction(tileOf(t, 1, "5z")))},
	)
}

func kokushiDealerGameInItsFourthRound(t *testing.T) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{copies(t, 0, "19m19p19s1234567z"), junk(t, 1), junk(t, 2), junk(t, 3)},
		Draws: copies(t, 1, "7z"),
	}
	tiles := wallTiles(t, w, seat(t, 0))
	g, _ := newGame(t, fixed(tiles, tiles, tiles, tiles), noStart())
	for range 3 {
		g, _ = script(t, g, act(seat(t, 0), play.KyuushuAction()))
		var refusal play.Option[play.Refusal]
		g, _, refusal = g.DealNextRound()
		if refusal.OK {
			t.Fatalf("DealNextRound refusal = %+v", refusal.Value)
		}
	}
	assertEqual(t, "finished rounds", len(g.History()), 3)
	return g
}

func TestAct_WhenTwoRoundEndingActionsBranchFromOneState_ShouldLeaveTheStateAndEachBranchsHistoryApart(t *testing.T) {
	build := func() game.Game { return kokushiDealerGameInItsFourthRound(t) }

	assertBranchesStayApart(t, build,
		[]testkit.SeatAction{act(seat(t, 0), play.KyuushuAction())},
		[]testkit.SeatAction{act(seat(t, 0), play.TsumoAction())},
	)
}

func TestHand_WhenTheSeatHasDrawn_ShouldReachItsBoundOfFourteenTiles(t *testing.T) {
	g := begun(t, stagedWall(t), noStart())

	assertEqual(t, "dealer tiles", len(g.Hand(seat(t, 0))), 14)
	assertEqual(t, "legal discards", len(g.LegalActions(seat(t, 0))), 14)
}

func TestMelds_WhenASeatCallsFourPons_ShouldReachItsBoundOfFourMelds(t *testing.T) {
	bystander := func(first int) []tile.TileID { return copies(t, first, "123456789p1379s") }
	junkDraws := slices.Concat(copies(t, 0, "5555z"), copies(t, 0, "6666z"), copies(t, 0, "7z"))
	called := []tile.TileID{tileOf(t, 2, "1m"), tileOf(t, 2, "2m"), tileOf(t, 2, "3m"), tileOf(t, 2, "4m")}
	draws := []tile.TileID{junkDraws[0]}
	for i, calledTile := range called {
		draws = append(draws, junkDraws[1+2*i], junkDraws[2+2*i], calledTile)
	}
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 0, "11223344m5m"), copies(t, 0, "1234z")),
			bystander(1), bystander(2), bystander(3),
		},
		Draws: draws,
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)

	var calls []play.Called
	for i := range called {
		g, _ = discardDrawn(t, g, 3)
		var events []play.Emitted
		g, events = script(t, g,
			act(seat(t, 0), firstPon(t, g, seat(t, 0))),
			act(seat(t, 0), play.DiscardAction(tileOf(t, 0, []string{"1z", "2z", "3z", "4z"}[i]))),
		)
		calls = append(calls, testkit.CalledMelds(events)...)
	}

	assertEqual(t, "calls", len(calls), 4)
	assertEqual(t, "hand", g.Hand(seat(t, 0)), copies(t, 0, "5m"))
	if err := g.CheckInvariants(); err != nil {
		t.Errorf("CheckInvariants error = %v", err)
	}
}
