package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const waitingSeat = 1

func waitingSeatFuriten(t *testing.T) []play.FuritenChanged {
	t.Helper()
	return []play.FuritenChanged{{Seat: seat(t, waitingSeat), Furiten: true}}
}

func waitingSeatFuritenCleared(t *testing.T) []play.FuritenChanged {
	t.Helper()
	return []play.FuritenChanged{{Seat: seat(t, waitingSeat), Furiten: false}}
}

func noFuritenChange() []play.FuritenChanged {
	return nil
}

func furitenStartWall(t *testing.T) testkit.StartWall {
	t.Helper()
	dealer := slices.Concat(copies(t, 3, "3p"), copies(t, 1, "1234567z"), copies(t, 2, "12z"), copies(t, 3, "246s"))
	return testkit.StartWall{Hands: [tile.SeatCount][]tile.TileID{
		dealer, copies(t, 0, "123456789p11s45m"), copies(t, 1, "123456789p2468s"), copies(t, 2, "123456789p3579s"),
	}}
}

func dealerThreeMan(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 1, "3m")
}

func dealerEast(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 1, "1z")
}

func lastChun(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 3, "7z")
}

func waitingSeatAfterOneGoAround(t *testing.T, waitingSeatDiscard, waitingSeatDraw tile.TileID, first func(tile.TileID) play.Action) (game.Game, []play.Emitted) {
	t.Helper()
	w := furitenStartWall(t)
	w.Draws = []tile.TileID{
		tileOf(t, 2, "7z"), waitingSeatDiscard, tileOf(t, 1, "9s"), tileOf(t, 3, "9s"), dealerThreeMan(t), waitingSeatDraw,
	}
	g, events := discardDrawn(t, begun(t, w, noStart()), 1)
	g, discarded := script(t, g, act(seat(t, waitingSeat), first(waitingSeatDiscard)))
	g, goneAround := discardDrawn(t, g, 2)
	return g, slices.Concat(events, discarded, goneAround)
}

func discardFuritenSeat(t *testing.T, waitingSeatDraw tile.TileID) game.Game {
	t.Helper()
	g, events := waitingSeatAfterOneGoAround(t, tileOf(t, 0, "3m"), waitingSeatDraw, play.DiscardAction)
	assertEqual(t, "furiten", testkit.FuritenChanges(events), waitingSeatFuriten(t))
	return g
}

func TestFuritenEvents_WhenTheGameStarts_ShouldEmitNone(t *testing.T) {
	source, err := testkit.FixedSetup(furitenStartWall(t), noStart())
	if err != nil {
		t.Fatalf("FixedSetup error = %v", err)
	}

	_, started := newGame(t, source, noStart())
	assertEqual(t, "furiten", testkit.FuritenChanges(started), noFuritenChange())
}

func TestFuritenEvents_WhenAnActionLeavesFuritenUnchanged_ShouldEmitNothing(t *testing.T) {
	g, events := waitingSeatAfterOneGoAround(t, tileOf(t, 3, "5z"), lastChun(t), play.DiscardAction)
	assertEqual(t, "furiten before", testkit.FuritenChanges(events), noFuritenChange())

	_, discarded := script(t, g, act(seat(t, 0), play.DiscardAction(dealerEast(t))))
	assertEqual(t, "furiten", testkit.FuritenChanges(discarded), noFuritenChange())
}

func TestFuritenEvents_WhenTheDiscardFuritenSeatDraws_ShouldKeepFuritenThroughItsTurn(t *testing.T) {
	g := discardFuritenSeat(t, lastChun(t))

	g, drawn := script(t, g, act(seat(t, 0), play.DiscardAction(dealerEast(t))))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, waitingSeat)))
	assertEqual(t, "furiten on draw", testkit.FuritenChanges(drawn), noFuritenChange())

	_, discarded := script(t, g, act(seat(t, waitingSeat), play.DiscardAction(lastChun(t))))
	assertEqual(t, "furiten on discard", testkit.FuritenChanges(discarded), noFuritenChange())
}

func TestFuritenEvents_WhenTheDiscardFuritenSeatCallsChi_ShouldKeepFuritenThroughItsMeldTurn(t *testing.T) {
	g := discardFuritenSeat(t, lastChun(t))

	g, prompted := script(t, g, act(seat(t, 0), play.DiscardAction(tileOf(t, 3, "3p"))))
	assertEqual(t, "awaiting call", g.Awaiting(), awaitingCall(seat(t, waitingSeat)))
	assertEqual(t, "furiten on prompt", testkit.FuritenChanges(prompted), noFuritenChange())

	chi := play.ChiAction([2]tile.TileID{tileOf(t, 0, "1p"), tileOf(t, 0, "2p")})
	g, called := script(t, g, act(seat(t, waitingSeat), chi))
	assertEqual(t, "awaiting turn", g.Awaiting(), awaitingTurn(seat(t, waitingSeat)))
	assertEqual(t, "furiten on chi", testkit.FuritenChanges(called), noFuritenChange())
}

func TestFuritenEvents_WhenTheSeatDeclinesRonWithAChi_ShouldShowFuritenThroughItsMeldTurn(t *testing.T) {
	g, events := waitingSeatAfterOneGoAround(t, tileOf(t, 3, "5z"), lastChun(t), play.DiscardAction)
	assertEqual(t, "furiten before", testkit.FuritenChanges(events), noFuritenChange())
	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(dealerThreeMan(t))))
	chi := play.ChiAction([2]tile.TileID{tileOf(t, 0, "4m"), tileOf(t, 0, "5m")})
	legal := g.LegalActions(seat(t, waitingSeat))
	if len(legal) == 0 || legal[0] != play.RonAction() || !containsAction(legal, chi) {
		t.Fatalf("legal actions = %v, want ron first and the chi", legal)
	}

	g, declined := script(t, g, act(seat(t, waitingSeat), chi))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, waitingSeat)))
	assertEqual(t, "hand size mod 3", len(g.Hand(seat(t, waitingSeat)))%3, 2)
	assertEqual(t, "furiten", testkit.FuritenChanges(declined), waitingSeatFuriten(t))
}

func TestFuritenEvents_WhenTheOwnDiscardDropsTheDiscardedWait_ShouldClearFuriten(t *testing.T) {
	g := discardFuritenSeat(t, tileOf(t, 0, "7m"))
	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(dealerEast(t))))

	_, discarded := script(t, g, act(seat(t, waitingSeat), play.DiscardAction(tileOf(t, 0, "4m"))))
	assertEqual(t, "last event", discarded[len(discarded)-1], play.Emitted{
		To: play.ToSeat(seat(t, waitingSeat)), Event: play.FuritenChanged{Seat: seat(t, waitingSeat), Furiten: false},
	})
	assertEqual(t, "furiten", testkit.FuritenChanges(discarded), waitingSeatFuritenCleared(t))
}

func TestFuritenEvents_WhenTheSeatDeclinesRonThenTakesItsTurn_ShouldShowFuritenThroughTheTurn(t *testing.T) {
	for _, c := range []struct {
		name                string
		first               func(tile.TileID) play.Action
		wantAfterOwnDiscard []play.FuritenChanged
	}{
		{name: "plain discard", first: play.DiscardAction, wantAfterOwnDiscard: waitingSeatFuritenCleared(t)},
		{name: "riichi", first: play.RiichiAction, wantAfterOwnDiscard: noFuritenChange()},
	} {
		t.Run(c.name, func(t *testing.T) {
			g, events := waitingSeatAfterOneGoAround(t, tileOf(t, 3, "5z"), lastChun(t), c.first)
			assertEqual(t, "furiten before", testkit.FuritenChanges(events), noFuritenChange())
			g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(dealerThreeMan(t))))
			assertEqual(t, "awaiting call", g.Awaiting(), awaitingCall(seat(t, waitingSeat)))

			g, declined := script(t, g, act(seat(t, waitingSeat), play.PassAction()))
			assertEqual(t, "awaiting turn", g.Awaiting(), awaitingTurn(seat(t, waitingSeat)))
			assertEqual(t, "hand size mod 3", len(g.Hand(seat(t, waitingSeat)))%3, 2)
			assertEqual(t, "furiten on pass", testkit.FuritenChanges(declined), waitingSeatFuriten(t))
			_, afterTurn := discardDrawn(t, g, 1)
			assertEqual(t, "furiten after own discard", testkit.FuritenChanges(afterTurn), c.wantAfterOwnDiscard)
		})
	}
}

func TestFuritenEvents_WhenFuritenStarts_ShouldTargetOnlyThatSeat(t *testing.T) {
	g, _ := waitingSeatAfterOneGoAround(t, tileOf(t, 3, "5z"), lastChun(t), play.DiscardAction)
	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(dealerThreeMan(t))))

	_, declined := script(t, g, act(seat(t, waitingSeat), play.PassAction()))

	var furiten []play.Emitted
	for _, emitted := range declined {
		if _, ok := emitted.Event.(play.FuritenChanged); ok {
			furiten = append(furiten, emitted)
		}
	}
	assertEqual(t, "furiten events", furiten, []play.Emitted{{
		To: play.ToSeat(seat(t, waitingSeat)), Event: play.FuritenChanged{Seat: seat(t, waitingSeat), Furiten: true},
	}})
}

func TestFuritenEvents_WhenTheRoundFinished_ShouldEmitNothing(t *testing.T) {
	g, _ := script(t, threePinWithTwoRonCallers(t), act(seat(t, 3), play.RonAction()))

	_, ended := script(t, g, act(seat(t, 0), play.PassAction()))
	if _, ok := ended[len(ended)-1].Event.(play.RoundEnded); !ok {
		t.Errorf("last event = %+v, want the round's end", ended[len(ended)-1].Event)
	}
	assertEqual(t, "furiten", testkit.FuritenChanges(ended), noFuritenChange())
}

type threePinHistory int

const (
	threePinNeverDiscarded threePinHistory = iota
	threePinDiscardedFirst
)

func riichiSeatWaitingOnThreePin(t *testing.T, history threePinHistory) game.Game {
	t.Helper()
	discardsTheWaitFirst := history == threePinDiscardedFirst
	riichiDiscard := tileOf(t, 0, "7z")
	firstDiscard := riichiDiscard
	if discardsTheWaitFirst {
		firstDiscard = tileOf(t, 1, "3p")
	}

	goArounds := []tile.TileID{tileOf(t, 1, "4z"), firstDiscard, tileOf(t, 1, "5z"), tileOf(t, 2, "5z")}
	if discardsTheWaitFirst {
		goArounds = append(goArounds, tileOf(t, 3, "5z"), riichiDiscard, tileOf(t, 0, "6z"), tileOf(t, 1, "6z"))
	}

	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 2, "3p"), copies(t, 0, "123456789s"), copies(t, 1, "123z")),
			copies(t, 0, "123456789m1255p"),
			slices.Concat(copies(t, 3, "3p"), copies(t, 1, "123456789s"), copies(t, 2, "123z")),
			slices.Concat(copies(t, 2, "123456789s"), copies(t, 3, "1234z")),
		},
		Draws: slices.Concat(goArounds, []tile.TileID{tileOf(t, 2, "6z"), tileOf(t, 1, "7z"), tileOf(t, 2, "7z")}),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	if discardsTheWaitFirst {
		g, _ = discardDrawn(t, g, tile.SeatCount)
	}

	g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(riichiDiscard)))
	g, _ = discardDrawn(t, g, 2)
	return g
}

func TestRiichiFuriten_WhenTheRiichiSeatDiscardedTheWinningTile_ShouldOfferNoRon(t *testing.T) {
	g := riichiSeatWaitingOnThreePin(t, threePinDiscardedFirst)

	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(tileOf(t, 2, "3p"))))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
}

func TestRiichiFuriten_WhenTheRiichiSeatPassesTheWinningTile_ShouldBlockRonForTheRestOfTheHand(t *testing.T) {
	g := riichiSeatWaitingOnThreePin(t, threePinNeverDiscarded)
	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(tileOf(t, 2, "3p"))))
	assertEqual(t, "awaiting call", g.Awaiting(), awaitingCall(seat(t, 1)))

	g, passed := script(t, g, act(seat(t, 1), play.PassAction()))
	assertEqual(t, "furiten on pass", testkit.FuritenChanges(passed), waitingSeatFuriten(t))
	if hand := g.Hand(seat(t, 1)); hand[len(hand)-1] != tileOf(t, 1, "7z") {
		t.Fatalf("last drawn tile = %v, want the second chun", hand[len(hand)-1])
	}

	g, _ = discardDrawn(t, g, 1)

	g, later := script(t, g, act(seat(t, 2), play.DiscardAction(tileOf(t, 3, "3p"))))
	assertEqual(t, "awaiting turn", g.Awaiting(), awaitingTurn(seat(t, 3)))
	assertEqual(t, "furiten later", testkit.FuritenChanges(later), noFuritenChange())
}

func TestTemporaryFuriten_WhenAWinningTileWithoutYakuPasses_ShouldBlockRonUntilTheOwnDiscard(t *testing.T) {
	threeManWithoutYaku, sixManWithIttsu, laterSixManWithIttsu := tileOf(t, 1, "3m"), tileOf(t, 1, "6m"), tileOf(t, 2, "6m")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 1, "12345678p9s"), copies(t, 2, "1234z")),
			slices.Concat(copies(t, 0, "12345789m9p22s"), copies(t, 1, "9p"), copies(t, 2, "9p")),
			copies(t, 0, "13456789s12345z"),
			slices.Concat([]tile.TileID{sixManWithIttsu}, copies(t, 0, "12345678p"), copies(t, 1, "1234z")),
		},
		Draws: []tile.TileID{
			tileOf(t, 1, "6z"), tileOf(t, 0, "7z"), threeManWithoutYaku, tileOf(t, 1, "5z"), tileOf(t, 1, "7z"),
			tileOf(t, 0, "6z"), laterSixManWithIttsu,
		},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 2)

	g, passed := discardDrawn(t, g, 1)
	assertEqual(t, "awaiting after the yakuless wait", g.Awaiting(), awaitingTurn(seat(t, 3)))
	assertEqual(t, "furiten on the yakuless wait", testkit.FuritenChanges(passed), waitingSeatFuriten(t))

	g, _ = script(t, g, act(seat(t, 3), play.DiscardAction(sixManWithIttsu)))
	assertEqual(t, "awaiting after the blocked ron", g.Awaiting(), awaitingTurn(seat(t, 0)))

	g, _ = discardDrawn(t, g, 1)
	g, ownDiscard := discardDrawn(t, g, 1)
	assertEqual(t, "furiten on the own discard", testkit.FuritenChanges(ownDiscard), waitingSeatFuritenCleared(t))

	g, _ = discardDrawn(t, g, 1)
	assertEqual(t, "awaiting the later ron", g.Awaiting(), awaitingCall(seat(t, 1)))
}

func ittsuSeatPassesThreeManThenSeatThreeDiscards(t *testing.T, seatThreeDraw tile.TileID, laterDraws []tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 1, "123456789s19m19p"),
			copies(t, 0, "123456789p45m55z"),
			slices.Concat(copies(t, 2, "123456789s"), copies(t, 0, "3m77z1z")),
			slices.Concat(copies(t, 3, "123456789s"), copies(t, 1, "2468p")),
		},
		Draws: slices.Concat(
			[]tile.TileID{tileOf(t, 0, "2z"), tileOf(t, 0, "3z"), tileOf(t, 1, "3m"), seatThreeDraw}, laterDraws),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 3)
	if legal := g.LegalActions(seat(t, waitingSeat)); len(legal) == 0 || legal[0] != play.RonAction() {
		t.Fatalf("legal actions = %v, want ron first", legal)
	}

	g, passed := script(t, g, act(seat(t, waitingSeat), play.PassAction()))
	assertEqual(t, "furiten on pass", testkit.FuritenChanges(passed), waitingSeatFuriten(t))

	g, _ = discardDrawn(t, g, 1)
	return g
}

func TestTemporaryFuriten_WhenTheSeatPonsAfterPassingRon_ShouldClearAtItsDiscard(t *testing.T) {
	fiveMan := tileOf(t, 1, "5m")
	g := ittsuSeatPassesThreeManThenSeatThreeDiscards(t, tileOf(t, 2, "5z"), []tile.TileID{fiveMan})
	assertEqual(t, "awaiting the pon", g.Awaiting(), awaitingCall(seat(t, waitingSeat)))

	g, called := script(t, g, act(seat(t, waitingSeat), firstPon(t, g, seat(t, waitingSeat))))
	assertEqual(t, "furiten on pon", testkit.FuritenChanges(called), noFuritenChange())

	g, discarded := script(t, g, act(seat(t, waitingSeat), play.DiscardAction(tileOf(t, 0, "4m"))))
	assertEqual(t, "furiten on discard", testkit.FuritenChanges(discarded), waitingSeatFuritenCleared(t))

	g, _ = script(t, g, act(seat(t, 2), play.DiscardAction(fiveMan)))
	assertEqual(t, "awaiting the ron", g.Awaiting(), awaitingCall(seat(t, waitingSeat)))
	if legal := g.LegalActions(seat(t, waitingSeat)); len(legal) == 0 || legal[0] != play.RonAction() {
		t.Errorf("legal actions = %v, want ron first", legal)
	}
}

func TestTemporaryFuriten_WhenAPonSkipsTheSeatsTurn_ShouldStillBlockRon(t *testing.T) {
	g := ittsuSeatPassesThreeManThenSeatThreeDiscards(t, tileOf(t, 2, "7z"), nil)
	assertEqual(t, "awaiting the pon", g.Awaiting(), awaitingCall(seat(t, 2)))

	g, called := script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))))
	assertEqual(t, "furiten on pon", testkit.FuritenChanges(called), noFuritenChange())

	g, _ = script(t, g, act(seat(t, 2), play.DiscardAction(tileOf(t, 0, "3m"))))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 3)))
}
