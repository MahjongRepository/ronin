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

func dealerGame(t *testing.T, dealer, draws []tile.TileID, w testkit.StartWall) game.Game {
	t.Helper()
	w.Hands = [tile.SeatCount][]tile.TileID{dealer, filler(t, 1), filler(t, 2), filler(t, 3)}
	w.Draws = draws
	return begun(t, w, noStart())
}

func rinshanDraw(t *testing.T, n int, id tile.TileID) play.Drew {
	t.Helper()
	return play.Drew{Seat: seat(t, n), Tile: id, Rinshan: true}
}

func TestClosedKan_WhenTheSeatHoldsThreeCopies_ShouldBeNotOfferedAndChangeNothing(t *testing.T) {
	triplet := copies(t, 0, "111m")
	g := dealerGame(t, slices.Concat(triplet, copies(t, 0, "123456789p1s")), []tile.TileID{tileOf(t, 0, "1z")},
		testkit.StartWall{})

	assertEqual(t, "kans", kans(g, seat(t, 0)), []play.Action(nil))
	assertRefused(t, g, seat(t, 0), play.KanAction(play.KanClosed, triplet[0]), notOfferedRefusal())
}

func onePonAndFourthCopy(t *testing.T) (game.Game, []tile.TileID) {
	t.Helper()
	oneMan := copies(t, 0, "1111m")
	dealer := slices.Concat(oneMan[:2], copies(t, 0, "123456789s"), copies(t, 0, "77z"))
	g := dealerPonFromSeatThree(t, dealer, oneMan[2], tileOf(t, 0, "7z"),
		slices.Concat(copies(t, 0, "666z"), oneMan[3:]), play.Option[tile.TileID]{})
	return g, oneMan
}

func TestAddedKan_WhenNoSeatMayRobIt_ShouldUpgradeThePonToAnAddedKanAndDrawTheRinshan(t *testing.T) {
	g, oneMan := onePonAndFourthCopy(t)
	g, _ = discardDrawn(t, g, 3)

	g, events := script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, oneMan[0])))

	assertEqual(t, "melds", testkit.CalledMelds(events), []play.Called{{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldAddedKan, Tiles: oneMan, Called: play.Some(oneMan[2]), From: play.Some(seat(t, 3)),
	}}})
	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"called", "drew", "drew", "drew", "drew"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	if slices.Contains(g.Hand(seat(t, 0)), oneMan[3]) {
		t.Error("the added copy is still in the hand")
	}
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}
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
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}
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

func threeKansOnTable(t *testing.T, table threeKans) game.Game {
	t.Helper()
	seatZero := slices.Concat(copies(t, 0, "1111s9999s"), []tile.TileID{eightPin(t, 1), eightPin(t, 2)}, table.eastExtras,
		[]tile.TileID{tileOf(t, 0, "7z")})
	seatOne := slices.Concat(copies(t, 0, "4444z"), copies(t, 0, "13579p2468s"))
	w := testkit.StartWall{
		Hands:   [tile.SeatCount][]tile.TileID{seatZero, seatOne, table.westHand, table.northHand},
		Draws:   slices.Concat([]tile.TileID{tileOf(t, 1, "7z"), tileOf(t, 1, "1z"), table.westDraw}, table.northDraws),
		Rinshan: []tile.TileID{tileOf(t, 2, "7z"), tileOf(t, 0, "9m"), tileOf(t, 1, "9m"), eightPin(t, 3)},
		KanDora: copies(t, 3, "1235z"),
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

func TestFourKans_WhenTheOpenFourthKansReplacementDiscardPasses_ShouldRevealTheKanDoraThenAbort(t *testing.T) {
	fiveMan := copies(t, 0, "5555m")
	g := threeKansOnTable(t, threeKans{
		eastExtras: copies(t, 0, "24m"),
		westHand:   slices.Concat(copies(t, 1, "13579p2468s"), copies(t, 0, "136z"), fiveMan[:1]),
		northHand:  slices.Concat(copies(t, 2, "234m567p345s"), []tile.TileID{eightPin(t, 0)}, fiveMan[1:]),
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
	assertEqual(t, "dora", testkit.DoraReveals(discard), copies(t, 3, "1235z")[3:])
	assertEqual(t, "result", roundResult(t, discard), play.RoundResult(play.Abortive{Kind: play.FourKans{}}))
}
