package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const liveTilesAfterTheFirstDraw = wall.LiveTilesAtDeal - 1

func pinWithHighSou(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789p6789s")
}

func secondDrawGame(t *testing.T, hand []tile.TileID, dora play.Option[tile.TileID], ura []tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			hand[:wall.StartingHandSize], pinWithHighSou(t, 1), pinWithHighSou(t, 2), pinWithHighSou(t, 3),
		},
		Draws: slices.Concat(copies(t, 2, "34z"), copies(t, 3, "34z"), hand[wall.StartingHandSize:]),
		Dora:  dora,
		Ura:   ura,
	}
	return begun(t, w, noStart())
}

func tsumoOnSecondDraw(t *testing.T, hand []tile.TileID, dora tile.TileID) play.WinResult {
	t.Helper()
	g, _ := discardDrawn(t, secondDrawGame(t, hand, play.Some(dora), nil), tile.SeatCount)
	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))
	return firstWin(t, events)
}

func baseDoraHand(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "123456789m12355s")
}

func honorPairHand(t *testing.T, honor string) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 0, "123456m789p123s"), copies(t, 0, honor), copies(t, 1, honor))
}

func TestDoraIndicator_WhenItIsNineMan_ShouldMakeOneManDora(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, baseDoraHand(t), tileOf(t, 1, "9m")).Dora.Dora, 1)
}

func TestDoraIndicator_WhenItIsFourSou_ShouldMakeFiveSouDora(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, baseDoraHand(t), tileOf(t, 0, "4s")).Dora.Dora, 2)
}

func TestDoraIndicator_WhenItIsNineSou_ShouldWrapToOneSou(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, baseDoraHand(t), tileOf(t, 0, "9s")).Dora.Dora, 1)
}

func TestDoraIndicator_WhenItIsNorth_ShouldMakeEastDora(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, honorPairHand(t, "1z"), tileOf(t, 0, "4z")).Dora.Dora, 2)
}

func TestDoraIndicator_WhenItIsEast_ShouldMakeSouthDora(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, honorPairHand(t, "2z"), tileOf(t, 0, "1z")).Dora.Dora, 2)
}

func TestDoraIndicator_WhenItIsChun_ShouldWrapToHaku(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, honorPairHand(t, "5z"), tileOf(t, 0, "7z")).Dora.Dora, 2)
}

func TestDoraIndicator_WhenItIsHaku_ShouldMakeHatsuDora(t *testing.T) {
	assertEqual(t, "dora", tsumoOnSecondDraw(t, honorPairHand(t, "6z"), tileOf(t, 0, "5z")).Dora.Dora, 2)
}

func redFiveManHand(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "11345678m123p789s")
}

func TestAkaDora_WhenARedFiveIsInTheHand_ShouldCountOneHan(t *testing.T) {
	win := tsumoOnSecondDraw(t, redFiveManHand(t), tileOf(t, 0, "1s"))

	assertEqual(t, "dora", win.Dora, play.DoraCount{AkaDora: 1})
}

func TestAkaDora_WhenTheRedFiveIsAlsoDora_ShouldStackWithTheDora(t *testing.T) {
	win := tsumoOnSecondDraw(t, redFiveManHand(t), tileOf(t, 1, "4m"))

	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 1, AkaDora: 1})
}

func TestAkaDora_WhenAllThreeRedFivesAreHeld_ShouldCountThreeHan(t *testing.T) {
	hand := copies(t, 0, "11345m345p345s111z")
	var redFives []int
	for _, held := range hand {
		if slices.Contains([]int{16, 52, 88}, held.Index()) {
			redFives = append(redFives, held.Index())
		}
	}
	assertEqual(t, "red fives held", len(redFives), 3)

	win := tsumoOnSecondDraw(t, hand, tileOf(t, 2, "1m"))

	assertEqual(t, "aka dora", win.Dora.AkaDora, 3)
}

func threeManDora(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 1, "2m")
}

func fiveSouUra(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 0, "4s")
}

func riichiTsumoOnSecondDraw(t *testing.T) play.WinResult {
	t.Helper()
	g := secondDrawGame(t, baseDoraHand(t), play.Some(threeManDora(t)), []tile.TileID{fiveSouUra(t)})
	riichiDiscard, _ := testkit.Drawn(g)
	g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(riichiDiscard)))
	g, _ = discardDrawn(t, g, 3)
	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))
	return firstWin(t, events)
}

func TestUraDora_WhenADoubleRiichiWinnerTsumos_ShouldRevealTheIndicatorAndAddItsHan(t *testing.T) {
	win := riichiTsumoOnSecondDraw(t)

	if !hasYaku(win.Yaku, play.YakuDaburuRiichi) {
		t.Errorf("yaku = %v, want daburu riichi", win.Yaku)
	}
	assertEqual(t, "ura indicators", win.UraIndicators, []tile.TileID{fiveSouUra(t)})
	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 1, AkaDora: 2, UraDora: 2})
}

func TestUraDora_WhenTheWinnerIsNotInRiichi_ShouldRevealNoneAndAddNoHan(t *testing.T) {
	g := secondDrawGame(t, baseDoraHand(t), play.Some(threeManDora(t)), []tile.TileID{fiveSouUra(t)})
	g, _ = discardDrawn(t, g, tile.SeatCount)

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	win := firstWin(t, events)
	assertEqual(t, "ura indicators", win.UraIndicators, []tile.TileID(nil))
	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 1, AkaDora: 2})
}

func TestHandValue_WhenRiichiIsFollowedByAKan_ShouldCountUraDoraUnderEachIndicator(t *testing.T) {
	eastQuad := copies(t, 0, "1111z")
	ura := []tile.TileID{tileOf(t, 1, "4s"), tileOf(t, 1, "1s")}
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m1235s"),
			slices.Concat(eastQuad, copies(t, 1, "123456789p")),
			pinWithHighSou(t, 2),
			pinWithHighSou(t, 3),
		},
		Draws:   slices.Concat(copies(t, 2, "34z"), copies(t, 3, "3z"), copies(t, 0, "7z"), copies(t, 1, "5s")),
		Rinshan: copies(t, 0, "2z"),
		Dora:    play.Some(tileOf(t, 1, "1m")),
		KanDora: copies(t, 1, "5m"),
		Ura:     ura,
	}
	g := begun(t, w, noStart())
	riichiDiscard, _ := testkit.Drawn(g)
	g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(riichiDiscard)))
	g, kan := script(t, g, act(seat(t, 1), play.KanAction(play.KanClosed, eastQuad[0])))
	assertEqual(t, "kan dora", testkit.DoraReveals(kan), copies(t, 1, "5m"))
	g, _ = discardDrawn(t, g, 3)

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	win := firstWin(t, events)
	assertEqual(t, "ura indicators", win.UraIndicators, ura)
	assertEqual(t, "dora", win.Dora, play.DoraCount{Dora: 2, AkaDora: 2, UraDora: 3})
}

func kanDoraWall(t *testing.T) testkit.StartWall {
	t.Helper()
	return testkit.StartWall{Rinshan: copies(t, 0, "99s"), KanDora: copies(t, 0, "78p")}
}

func firstGoAroundToSeatThree(t *testing.T, fourth tile.TileID) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 0, "123z"), []tile.TileID{fourth})
}

func oneManDiscardedBySeatThree(t *testing.T, dealer []tile.TileID) game.Game {
	t.Helper()
	g := dealerGame(t, dealer, firstGoAroundToSeatThree(t, tileOf(t, 3, "1m")), kanDoraWall(t))
	g, _ = discardDrawn(t, g, tile.SeatCount)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))
	return g
}

func discardRinshan(t *testing.T, g game.Game) []play.Emitted {
	t.Helper()
	_, events := discardDrawn(t, g, 1)
	return events
}

func TestKanDora_WhenAClosedKanIsDeclared_ShouldRevealItsIndicatorAtOnce(t *testing.T) {
	oneMan := copies(t, 0, "1111m")
	g := dealerGame(t, slices.Concat(oneMan, copies(t, 1, "123456789p")), copies(t, 1, "2s"), kanDoraWall(t))

	g, kan := script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, oneMan[0])))

	assertEqual(t, "kinds", testkit.EventKinds(kan), []string{"called", "dora_revealed", "drew", "drew", "drew", "drew"})
	assertEqual(t, "kan dora", testkit.DoraReveals(kan), copies(t, 0, "7p"))
	assertEqual(t, "dora on discard", testkit.DoraReveals(discardRinshan(t, g)), []tile.TileID(nil))
}

func TestKanDora_WhenAnOpenKanIsDeclared_ShouldDeferItsIndicatorToTheReplacementDiscard(t *testing.T) {
	g := oneManDiscardedBySeatThree(t, slices.Concat(copies(t, 0, "111m"), copies(t, 1, "123456789p2s")))

	g, kan := script(t, g, act(seat(t, 0), play.KanAction(play.KanOpen, tileOf(t, 3, "1m"))))

	assertEqual(t, "kan kinds", testkit.EventKinds(kan), []string{"called", "drew", "drew", "drew", "drew"})
	assertEqual(t, "rinshan", testkit.DrawnRinshan(kan), []play.Drew{rinshanDraw(t, 0, tileOf(t, 0, "9s"))})

	discard := discardRinshan(t, g)

	assertEqual(t, "discard kinds", testkit.EventKinds(discard)[:2], []string{"discarded", "dora_revealed"})
	assertEqual(t, "kan dora", testkit.DoraReveals(discard), copies(t, 0, "7p"))
}

func TestKanDora_WhenAnAddedKanIsDeclared_ShouldDeferItsIndicatorToTheReplacementDiscard(t *testing.T) {
	dealer := slices.Concat(copies(t, 0, "11m"), copies(t, 1, "123456789p2s"), copies(t, 0, "6z"))
	draws := slices.Concat(firstGoAroundToSeatThree(t, tileOf(t, 2, "1m")),
		[]tile.TileID{tileOf(t, 0, "4z"), tileOf(t, 1, "1z"), tileOf(t, 1, "2z"), tileOf(t, 3, "1m")})
	g, _ := discardDrawn(t, dealerGame(t, dealer, draws, kanDoraWall(t)), tile.SeatCount)
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "6z"))))
	g, _ = discardDrawn(t, g, 3)

	g, kan := script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, tileOf(t, 3, "1m"))))

	assertEqual(t, "melds", testkit.CalledMelds(kan), []play.Called{{Seat: seat(t, 0), Meld: play.MeldView{
		Kind: play.MeldAddedKan, Tiles: copies(t, 0, "1111m"), Called: play.Some(tileOf(t, 2, "1m")), From: play.Some(seat(t, 3)),
		Added: play.Some(tileOf(t, 3, "1m")),
	}}})
	assertEqual(t, "dora on kan", testkit.DoraReveals(kan), []tile.TileID(nil))
	assertEqual(t, "dora on discard", testkit.DoraReveals(discardRinshan(t, g)), copies(t, 0, "7p"))
}

func ninePinOpenKanBySeatOne(t *testing.T, seatTwo, seatThree []tile.TileID, w testkit.StartWall) game.Game {
	t.Helper()
	ninePin := copies(t, 0, "9999p")
	w.Hands = [tile.SeatCount][]tile.TileID{
		copies(t, 0, "123456789m2345z"),
		slices.Concat(ninePin[:3], copies(t, 0, "1z"), copies(t, 1, "123456789s")),
		seatTwo,
		seatThree,
	}
	w.Draws = ninePin[3:]
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	assertEqual(t, "legal actions", g.LegalActions(seat(t, 1)), []play.Action{
		play.KanAction(play.KanOpen, ninePin[3]), firstPon(t, g, seat(t, 1)), play.PassAction(),
	})
	g, _ = script(t, g, act(seat(t, 1), play.KanAction(play.KanOpen, ninePin[3])))
	return g
}

func TestKanDora_WhenTheOpenKansReplacementDiscardIsPonned_ShouldRevealTheDoraAtTheDiscard(t *testing.T) {
	kanDoraIndicator := tileOf(t, 1, "9m")
	g := ninePinOpenKanBySeatOne(t,
		slices.Concat(copies(t, 2, "123456789s"), copies(t, 1, "2345z")),
		slices.Concat(copies(t, 1, "1z"), copies(t, 2, "1z"), copies(t, 3, "123456789s"), copies(t, 2, "23z")),
		testkit.StartWall{Rinshan: copies(t, 0, "4p"), KanDora: []tile.TileID{kanDoraIndicator}},
	)

	g, discard := script(t, g, act(seat(t, 1), play.DiscardAction(tileOf(t, 0, "1z"))))

	assertEqual(t, "dora on discard", testkit.DoraReveals(discard), []tile.TileID{kanDoraIndicator})
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 3)))

	_, pon := script(t, g, act(seat(t, 3), firstPon(t, g, seat(t, 3))))

	assertEqual(t, "dora on pon", testkit.DoraReveals(pon), []tile.TileID(nil))
	if called := testkit.CalledMelds(pon); len(called) == 0 || called[0].Meld.Kind != play.MeldPon {
		t.Errorf("called melds = %+v, want a pon", called)
	}
}

func TestKanDora_WhenTheOpenKansReplacementDiscardIsRonned_ShouldCountTheNewDora(t *testing.T) {
	g := ninePinOpenKanBySeatOne(t,
		slices.Concat(copies(t, 1, "123456789m"), copies(t, 1, "1z"), copies(t, 2, "1z"), copies(t, 0, "55p")),
		slices.Concat(copies(t, 3, "123456789s"), copies(t, 1, "2345z")),
		testkit.StartWall{Rinshan: copies(t, 2, "9m"), Dora: play.Some(tileOf(t, 0, "1s")), KanDora: copies(t, 0, "4p")},
	)
	g, _ = script(t, g, act(seat(t, 1), play.DiscardAction(tileOf(t, 0, "1z"))))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 2)))

	_, events := script(t, g, act(seat(t, 2), play.RonAction()))

	assertEqual(t, "dora", firstWin(t, events).Dora.Dora, 2)
}

func TestKanDora_WhenAClosedKanFollowsAnOpenKan_ShouldRevealBothIndicatorsBeforeItsDraw(t *testing.T) {
	twoMan := copies(t, 0, "2222m")
	g := oneManDiscardedBySeatThree(t, slices.Concat(copies(t, 0, "111m"), twoMan, copies(t, 1, "123456p")))
	g, openKan := script(t, g, act(seat(t, 0), play.KanAction(play.KanOpen, tileOf(t, 3, "1m"))))
	assertEqual(t, "dora on open kan", testkit.DoraReveals(openKan), []tile.TileID(nil))

	g, closedKan := script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, twoMan[0])))

	assertEqual(t, "kinds", testkit.EventKinds(closedKan),
		[]string{"called", "dora_revealed", "dora_revealed", "drew", "drew", "drew", "drew"})
	assertEqual(t, "kan dora", testkit.DoraReveals(closedKan), copies(t, 0, "78p"))
	assertEqual(t, "rinshan", testkit.DrawnRinshan(closedKan), []play.Drew{rinshanDraw(t, 0, tileOf(t, 1, "9s"))})
	assertEqual(t, "dora on discard", testkit.DoraReveals(discardRinshan(t, g)), []tile.TileID(nil))
}

func openKanAfterTwoManPon(t *testing.T, rest []tile.TileID, w testkit.StartWall) game.Game {
	t.Helper()
	dealer := slices.Concat(copies(t, 0, "111m"), []tile.TileID{tileOf(t, 0, "2m"), tileOf(t, 1, "2m"), tileOf(t, 3, "2m")},
		rest, copies(t, 0, "6z"))
	draws := slices.Concat(firstGoAroundToSeatThree(t, tileOf(t, 2, "2m")),
		[]tile.TileID{tileOf(t, 0, "4z"), tileOf(t, 1, "1z"), tileOf(t, 3, "1m")})
	g, _ := discardDrawn(t, dealerGame(t, dealer, draws, w), tile.SeatCount)
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "6z"))))
	g, _ = discardDrawn(t, g, 3)
	g, openKan := script(t, g, act(seat(t, 0), play.KanAction(play.KanOpen, tileOf(t, 3, "1m"))))
	assertEqual(t, "dora on open kan", testkit.DoraReveals(openKan), []tile.TileID(nil))
	return g
}

func TestKanDora_WhenAnAddedKanFollowsAnOpenKan_ShouldRevealTheOpenKansIndicatorAtItsDraw(t *testing.T) {
	g := openKanAfterTwoManPon(t, copies(t, 1, "123456p"), kanDoraWall(t))

	g, addedKan := script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, tileOf(t, 3, "2m"))))

	assertEqual(t, "kinds", testkit.EventKinds(addedKan), []string{"called", "dora_revealed", "drew", "drew", "drew", "drew"})
	assertEqual(t, "dora on added kan", testkit.DoraReveals(addedKan), copies(t, 0, "7p"))
	assertEqual(t, "rinshan", testkit.DrawnRinshan(addedKan), []play.Drew{rinshanDraw(t, 0, tileOf(t, 1, "9s"))})
	assertEqual(t, "dora on discard", testkit.DoraReveals(discardRinshan(t, g)), copies(t, 0, "8p"))
}

func TestRinshanTsumo_WhenAnAddedKanFollowsAnOpenKan_ShouldCountOnlyTheOpenKansDora(t *testing.T) {
	g := openKanAfterTwoManPon(t, copies(t, 0, "234678p"), testkit.StartWall{
		Rinshan: copies(t, 0, "99p"), Dora: play.Some(tileOf(t, 0, "9s")), KanDora: copies(t, 1, "12p"),
	})
	g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, tileOf(t, 3, "2m"))))

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	win := firstWin(t, events)
	if !hasYaku(win.Yaku, play.YakuRinshan) {
		t.Errorf("yaku = %v, want rinshan", win.Yaku)
	}
	assertEqual(t, "dora", win.Dora.Dora, 1)
}

func safeFillers(t *testing.T, w testkit.StartWall, count int, excluded ...tile.Kind) []tile.TileID {
	t.Helper()
	var suited, honors []tile.TileID
	for _, free := range w.UnplacedTiles() {
		switch kind := free.Kind(); {
		case slices.Contains(excluded, kind):
		case kind.IsHonor():
			honors = append(honors, free)
		default:
			suited = append(suited, free)
		}
	}
	fillers := slices.Concat(suited, honors)
	if len(fillers) < count {
		t.Fatalf("%d safe fillers are left, want %d", len(fillers), count)
	}
	return fillers[:count]
}

func lastEast(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 1, "1z")
}

func openKanOnTheLastLiveTile(t *testing.T, rinshan tile.TileID) game.Game {
	t.Helper()
	nineSou := tileOf(t, 0, "9s")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat([]tile.TileID{nineSou}, copies(t, 1, "12345678s2356z")),
			slices.Concat(copies(t, 1, "999s"), copies(t, 3, "123456789p"), copies(t, 0, "4z")),
			copies(t, 0, "123456789m444p1z"),
			slices.Concat(copies(t, 2, "12345678s2356z"), copies(t, 3, "1z")),
		},
		Rinshan: []tile.TileID{rinshan},
		Dora:    play.Some(tileOf(t, 3, "7z")),
	}
	w.Draws = safeFillers(t, w, liveTilesAfterTheFirstDraw, kindOf(t, "1z"), kindOf(t, "4z"))
	g := playDefaultsWhileLiveTilesExceed(t, begun(t, w, noStart()), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 0)))
	g, _ = script(t, g,
		act(seat(t, 0), play.DiscardAction(nineSou)),
		act(seat(t, 1), play.KanAction(play.KanOpen, nineSou)),
	)
	assertEqual(t, "live tiles", g.LiveTiles(), 0)
	return g
}

func TestRinshan_WhenAnOpenKanTakesTheLastLiveTile_ShouldWinWithoutHaitei(t *testing.T) {
	rinshan := tileOf(t, 1, "4z")
	g := openKanOnTheLastLiveTile(t, rinshan)
	decision, ok := g.Decision(seat(t, 1))
	if !ok {
		t.Fatal("seat 1 has no decision")
	}
	assertEqual(t, "context", decision.Context, play.DecisionContext(play.TurnAfterDraw{Drawn: rinshan, Rinshan: true}))

	_, events := script(t, g, act(seat(t, 1), play.TsumoAction()))

	assertEqual(t, "yaku", firstWin(t, events).Yaku, []play.YakuID{play.YakuRinshan, play.YakuIttsu})
}

func TestHoutei_WhenTheDiscardAfterAKanOnTheLastLiveTileIsRonned_ShouldAllowOnlyRonAndAwardHoutei(t *testing.T) {
	g := openKanOnTheLastLiveTile(t, lastEast(t))

	g, _ = script(t, g, act(seat(t, 1), play.DiscardAction(lastEast(t))))

	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 2)))
	assertEqual(t, "legal actions", g.LegalActions(seat(t, 2)), []play.Action{play.RonAction(), play.PassAction()})

	_, events := script(t, g, act(seat(t, 2), play.RonAction()))

	win := firstWin(t, events)
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuHoutei, play.YakuIttsu})
	assertEqual(t, "aka dora", win.Dora.AkaDora, 1)
}

func TestRinshan_WhenTheClosedKansReplacementTileCompletesTheHand_ShouldAwardItWithOneOrTwoLiveTiles(t *testing.T) {
	for _, tc := range []struct{ kanSeat, liveTilesBeforeKan int }{{3, 2}, {0, 1}} {
		kanSeat := seat(t, tc.kanSeat)
		oneMan, north := copies(t, 0, "1111m"), copies(t, 0, "44z")
		var hands [tile.SeatCount][]tile.TileID
		bystanderCopy := 0
		for _, handSeat := range tile.Seats() {
			if handSeat == kanSeat {
				hands[handSeat.Index()] = slices.Concat(oneMan, copies(t, 0, "123456789p"))
				continue
			}
			bystanderCopy++
			hands[handSeat.Index()] = copies(t, bystanderCopy, "123456789p1234s")
		}
		w := testkit.StartWall{Hands: hands, Rinshan: north[1:]}
		fillers := safeFillers(t, w, liveTilesAfterTheFirstDraw-tc.liveTilesBeforeKan, kindOf(t, "1s"), kindOf(t, "4s"), north[0].Kind())
		w.Draws = slices.Concat(fillers, north[:1])
		g := playDefaultsWhileLiveTilesExceed(t, begun(t, w, noStart()), tc.liveTilesBeforeKan)
		assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(kanSeat))
		if hand := g.Hand(kanSeat); hand[len(hand)-1] != north[0] {
			t.Fatalf("kan seat %d: last drawn tile = %v, want the first north", tc.kanSeat, hand[len(hand)-1])
		}

		g, kan := script(t, g, act(kanSeat, play.KanAction(play.KanClosed, oneMan[0])))
		assertEqual(t, "rinshan", testkit.DrawnRinshan(kan), []play.Drew{rinshanDraw(t, tc.kanSeat, north[1])})

		_, events := script(t, g, act(kanSeat, play.TsumoAction()))

		win := firstWin(t, events)
		assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuRinshan, play.YakuIttsu})
		assertEqual(t, "aka dora", win.Dora.AkaDora, 1)
	}
}
