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

func kanAfterGoAround(t *testing.T, seatZero, seatThree []tile.TileID) (game.Game, []play.Emitted) {
	t.Helper()
	later := []tile.TileID{hatsu(t, 1), hatsu(t, 2), hatsu(t, 3), threePin(t, 3)}
	g, _ := discardDrawn(t, begun(t, threePinWall(t, seatZero, seatThree, later), noStart()), 2)
	for _, other := range awaitedSeats(g) {
		if other != seat(t, 2) {
			g, _ = script(t, g, act(other, play.PassAction()))
		}
	}
	g, _ = script(t, g,
		act(seat(t, 2), firstPon(t, g, seat(t, 2))),
		act(seat(t, 2), play.DiscardAction(seatTwoDiscardAfterPon(t))),
	)
	g, _ = discardDrawn(t, g, 3)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	return script(t, g, act(seat(t, 2), play.KanAction(play.KanAdded, threePin(t, 3))))
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

func otherPenchanOnThreePin(t *testing.T) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 1, "123456789m12p"), copies(t, 2, "55p"))
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

func TestChankan_WhenEveryRobberPasses_ShouldLetTheAddedKanStandWithItsRinshanDrawAndDoraAtTheNextDiscard(t *testing.T) {
	g, declared := kanAfterGoAround(t, chankanBystander(t, 2), otherPenchanOnThreePin(t))
	assertEqual(t, "declared", testkit.CalledMelds(declared), []play.Called{threePinAddedKan(t)})

	g, passed := script(t, g, act(seat(t, 3), play.PassAction()))

	assertEqual(t, "melds", testkit.CalledMelds(passed), []play.Called(nil))
	assertEqual(t, "dora", testkit.DoraReveals(passed), []tile.TileID(nil))
	assertEqual(t, "kinds", testkit.EventKinds(passed)[:4], []string{"drew", "drew", "drew", "drew"})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}

	_, discarded := discardDrawn(t, g, 1)

	assertEqual(t, "discard kinds", testkit.EventKinds(discarded)[:2], []string{"discarded", "dora_revealed"})
	assertEqual(t, "dora count", len(testkit.DoraReveals(discarded)), 1)
}

func TestKokushiChankan_WhenTheClosedKanIsRobbed_ShouldAnnounceTheKanThenEndTheRoundWithNoDora(t *testing.T) {
	oneMan := copies(t, 0, "1111m")
	dealer := slices.Concat(oneMan[:3], copies(t, 1, "123456789p"), copies(t, 1, "2s"))
	w := testkit.StartWall{
		Hands:   [tile.SeatCount][]tile.TileID{dealer, copies(t, 0, "99m19p19s1234567z"), filler(t, 2), filler(t, 3)},
		Draws:   oneMan[3:],
		KanDora: []tile.TileID{tileOf(t, 0, "7s")},
	}
	g, declared := script(t, begun(t, w, noStart()), act(seat(t, 0), play.KanAction(play.KanClosed, oneMan[0])))
	assertEqual(t, "melds", testkit.CalledMelds(declared), []play.Called{{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldClosedKan, Tiles: oneMan,
	}}})
	assertEqual(t, "dora", testkit.DoraReveals(declared), []tile.TileID(nil))
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership after the kan error = %v", err)
	}

	g, robbed := script(t, g, act(seat(t, 1), play.RonAction()))

	assertEqual(t, "kinds", testkit.EventKinds(robbed), []string{"round_ended", "game_ended"})
	win := firstWin(t, robbed)
	assertEqual(t, "win", [3]any{win.Winner, win.Loser, win.WinTile}, [3]any{seat(t, 1), play.Some(seat(t, 0)), oneMan[0]})
	if !slices.Contains(win.Yaku, play.YakuKokushiMusou) {
		t.Errorf("yaku = %v, want kokushi musou", win.Yaku)
	}
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership after the ron error = %v", err)
	}
}
