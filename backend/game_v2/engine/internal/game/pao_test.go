package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func paoDealerGame(t *testing.T, dealer, draws, rinshan []tile.TileID) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			dealer, copies(t, 1, "123456789p1234s"), copies(t, 2, "123456789p1234s"), copies(t, 3, "123456789p1234s"),
		},
		Draws:   draws,
		Rinshan: rinshan,
	}
	return begun(t, w, noStart())
}

func ponAndDiscard(t *testing.T, g game.Game, discard tile.TileID) game.Game {
	t.Helper()
	g, _ = discardDrawn(t, g, 1)
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(discard)))
	return g
}

func dragonDraws(t *testing.T, seatOneDraws []tile.TileID) []tile.TileID {
	t.Helper()
	return slices.Concat([]tile.TileID{tileOf(t, 0, "3z")}, seatOneDraws, copies(t, 0, "246m"),
		[]tile.TileID{tileOf(t, 1, "9s")})
}

func TestPao_WhenAnOpenKanCompletesTheThirdDragon_ShouldBeAnnouncedToAllRightAfterTheCall(t *testing.T) {
	dealer := slices.Concat(copies(t, 0, "5566777z"), copies(t, 0, "234p9s"), copies(t, 0, "12z"))
	draws := dragonDraws(t, []tile.TileID{tileOf(t, 2, "5z"), tileOf(t, 2, "6z"), tileOf(t, 3, "7z")})
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, []tile.TileID{tileOf(t, 3, "4z")}), 1)
	g = ponAndDiscard(t, g, tileOf(t, 0, "1z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "2z"))
	g, _ = discardDrawn(t, g, 1)
	followed := g.SeatView(seat(t, 2)).Record

	g, events := script(t, g, act(seat(t, 0), play.KanAction(play.KanOpen, tileOf(t, 3, "7z"))))

	assertEqual(t, "kinds", testkit.EventKinds(events)[:2], []string{"called", "pao_assigned"})
	assertEqual(t, "pao", events[1], play.Emitted{To: play.ToAll(), Event: play.PaoAssigned{
		Seat: seat(t, 0), Liable: seat(t, 1),
	}})
	var paoSeats [tile.SeatCount]play.Option[tile.Seat]
	for i, player := range g.SeatView(seat(t, 2)).Record.Players {
		paoSeats[i] = player.Pao
	}
	assertEqual(t, "pao in the view", paoSeats, [tile.SeatCount]play.Option[tile.Seat]{play.Some(seat(t, 1))})
	for _, e := range events {
		followed = record.Apply(followed, e)
	}
	assertEqual(t, "record following the kan", followed, g.SeatView(seat(t, 2)).Record)
}

func dragonPons() []string {
	return []string{"5z", "6z", "7z"}
}

func tankiOnNineSou(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "234p9s")
}

func paoExtras(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "444z")
}

type paoTable struct {
	winner, pao         tile.Seat
	closed              []tile.TileID
	otherWinner         play.Option[tile.Seat]
	winTile             tile.TileID
	ronDiscarder        play.Option[tile.Seat]
	honba, riichiSticks int
}

func (pt paoTable) lastSeat() tile.Seat {
	if pt.ronDiscarder.OK {
		return pt.ronDiscarder.Value
	}
	return pt.winner
}

func paoDraws(t *testing.T, table paoTable) []tile.TileID {
	t.Helper()
	var junk []tile.TileID
	for first := range tile.CopiesPerKind {
		junk = append(junk, copies(t, first, "2345678s")...)
	}
	var draws []tile.TileID
	drawJunkUntil := func(current, stop tile.Seat) {
		for ; current != stop; current = current.Next() {
			draws, junk = append(draws, junk[0]), junk[1:]
		}
	}
	current := seat(t, 0)
	for _, dragon := range dragonPons() {
		drawJunkUntil(current, table.pao)
		draws = append(draws, tileOf(t, 2, dragon))
		current = table.winner.Next()
	}
	drawJunkUntil(current, table.lastSeat())
	return append(draws, table.winTile)
}

func threeDragonPonsFedByThePaoSeat(t *testing.T, table paoTable) game.Game {
	t.Helper()
	winnerHand := slices.Concat(copies(t, 0, "556677z"), table.closed, paoExtras(t))
	var hands [tile.SeatCount][]tile.TileID
	fillerCopy := 1
	for _, s := range tile.Seats() {
		switch {
		case s == table.winner:
			hands[s.Index()] = winnerHand
		case table.otherWinner.OK && s == table.otherWinner.Value:
			hands[s.Index()] = slices.Concat(copies(t, 0, "123456789m11p"), copies(t, 2, "99s"))
		default:
			hands[s.Index()] = copies(t, fillerCopy, "123456789m5678p")
			fillerCopy++
		}
	}
	w := testkit.StartWall{Hands: hands, Draws: paoDraws(t, table), Dora: play.Some(tileOf(t, 0, "1s"))}
	g := begun(t, w, play.Some(testkit.EastStart(sticksPaidScores(table.riichiSticks), table.honba, table.riichiSticks)))

	for _, extra := range paoExtras(t) {
		g = discardDrawnUntilTurnOf(t, g, table.pao)
		g, _ = discardDrawn(t, g, 1)
		g, _ = script(t, g, act(table.winner, firstPon(t, g, table.winner)), act(table.winner, play.DiscardAction(extra)))
	}
	g = discardDrawnUntilTurnOf(t, g, table.lastSeat())
	if table.ronDiscarder.OK {
		g, _ = discardDrawn(t, g, 1)
	}
	return g
}

func paoTsumo(t *testing.T, table paoTable) play.WinResult {
	t.Helper()
	_, events := script(t, threeDragonPonsFedByThePaoSeat(t, table), act(table.winner, play.TsumoAction()))
	tsumo, ok := roundResult(t, events).(play.Tsumo)
	if !ok {
		t.Fatalf("result = %+v, want a tsumo", roundResult(t, events))
	}
	return tsumo.Win
}

func paoRons(t *testing.T, table paoTable) ([]play.WinResult, [tile.SeatCount]int) {
	t.Helper()
	g := threeDragonPonsFedByThePaoSeat(t, table)
	prompt, ok := g.Awaiting().(play.AwaitingCall)
	if !ok {
		t.Fatalf("awaiting = %+v, want the win tile offered to ron", g.Awaiting())
	}
	answers := make([]testkit.SeatAction, len(prompt.Seats))
	for i, caller := range prompt.Seats {
		answers[i] = act(caller, play.RonAction())
	}
	_, events := script(t, g, answers...)
	ron := ronResult(t, events)
	return ron.Wins, ron.TotalScoreChanges()
}

func paoRonTable(t *testing.T, winner, pao, discarder tile.Seat) paoTable {
	t.Helper()
	return paoTable{
		winner: winner, pao: pao, closed: tankiOnNineSou(t), winTile: tileOf(t, 1, "9s"),
		ronDiscarder: play.Some(discarder),
	}
}

func daisangenAndTsuuiisouTable(t *testing.T, ronDiscarder play.Option[tile.Seat]) paoTable {
	t.Helper()
	return paoTable{
		winner: seat(t, 0), pao: seat(t, 3), closed: copies(t, 0, "1112z"), winTile: tileOf(t, 1, "2z"),
		ronDiscarder: ronDiscarder, honba: 1,
	}
}

func paoSeats(wins []play.WinResult) []play.Option[tile.Seat] {
	pao := make([]play.Option[tile.Seat], len(wins))
	for i, win := range wins {
		pao[i] = win.Pao
	}
	return pao
}

func scoreChangesByWin(wins []play.WinResult) [][tile.SeatCount]int {
	changes := make([][tile.SeatCount]int, len(wins))
	for i, win := range wins {
		changes[i] = win.ScoreChanges
	}
	return changes
}

func TestPao_WhenANonDealerTsumosWithHonba_ShouldChargeThePaoSeatEverything(t *testing.T) {
	table := paoRonTable(t, seat(t, 1), seat(t, 2), seat(t, 0))
	table.honba, table.riichiSticks, table.ronDiscarder = 1, 1, play.Option[tile.Seat]{}

	win := paoTsumo(t, table)

	assertEqual(t, "pao", win.Pao, play.Some(seat(t, 2)))
	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuDaisangen})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 1)
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{0, 33300, -32300, 0})
}

func TestPao_WhenTheDealerTsumosAStackedYakuman_ShouldChargeThePaoSeatTheWholeHandAndHonba(t *testing.T) {
	win := paoTsumo(t, daisangenAndTsuuiisouTable(t, play.Option[tile.Seat]{}))

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuDaisangen, play.YakuTsuuiisou})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 2)
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{96300, 0, 0, -96300})
}

func TestPao_WhenTheDealerRonsOffAnotherSeat_ShouldSplitTheHandAndGiveTheSticksToTheWinner(t *testing.T) {
	table := paoRonTable(t, seat(t, 0), seat(t, 2), seat(t, 1))
	table.riichiSticks = 1

	wins, changes := paoRons(t, table)

	assertEqual(t, "pao", wins[0].Pao, play.Some(seat(t, 2)))
	assertEqual(t, "score changes", changes, [tile.SeatCount]int{49000, -24000, -24000, 0})
}

func TestPao_WhenTheRonIsOffThePaoSeat_ShouldChargeItInFull(t *testing.T) {
	table := paoRonTable(t, seat(t, 1), seat(t, 3), seat(t, 3))
	table.honba = 1

	wins, changes := paoRons(t, table)

	assertEqual(t, "pao", wins[0].Pao, play.Some(seat(t, 3)))
	assertEqual(t, "score changes", changes, [tile.SeatCount]int{0, 32300, 0, -32300})
}

func TestPao_WhenTheRonIsOffAnotherSeatWithHonba_ShouldChargeTheWholeHonbaToThePaoSeat(t *testing.T) {
	table := paoRonTable(t, seat(t, 1), seat(t, 3), seat(t, 2))
	table.honba = 1

	_, changes := paoRons(t, table)

	assertEqual(t, "score changes", changes, [tile.SeatCount]int{0, 32300, -16000, -16300})
}

func TestPao_WhenTheDealerRonsAStackedYakuman_ShouldChargeThePaoSeatHalfTheWholeHandAndHonba(t *testing.T) {
	wins, changes := paoRons(t, daisangenAndTsuuiisouTable(t, play.Some(seat(t, 1))))

	assertEqual(t, "yaku", wins[0].Yaku, []play.YakuID{play.YakuDaisangen, play.YakuTsuuiisou})
	assertEqual(t, "score changes", changes, [tile.SeatCount]int{96300, -48000, 0, -48300})
}

func TestPao_WhenThePaoWinnerHeadsADoubleRonWithHonba_ShouldChargeItsHonbaToThePaoSeat(t *testing.T) {
	table := paoRonTable(t, seat(t, 0), seat(t, 2), seat(t, 3))
	table.otherWinner, table.honba = play.Some(seat(t, 1)), 1

	wins, changes := paoRons(t, table)

	assertEqual(t, "pao", paoSeats(wins), []play.Option[tile.Seat]{play.Some(seat(t, 2)), {}})
	assertEqual(t, "changes by win", scoreChangesByWin(wins), [][tile.SeatCount]int{
		{48300, 0, -24300, -24000}, {0, 5200, 0, -5200},
	})
	assertEqual(t, "score changes", changes, [tile.SeatCount]int{48300, 5200, -24300, -29200})
}

func TestPao_WhenThePaoWinnerIsTheFartherOfADoubleRon_ShouldChargeThePaoSeatNoHonba(t *testing.T) {
	table := paoRonTable(t, seat(t, 2), seat(t, 3), seat(t, 0))
	table.otherWinner, table.honba = play.Some(seat(t, 1)), 1

	wins, changes := paoRons(t, table)

	assertEqual(t, "pao", paoSeats(wins), []play.Option[tile.Seat]{{}, play.Some(seat(t, 3))})
	assertEqual(t, "score changes", changes, [tile.SeatCount]int{-21500, 5500, 32000, -16000})
}

func TestPao_WhenTheLiableSeatIsTheOtherWinnerOfADoubleRon_ShouldChargeItHalfTheYakuman(t *testing.T) {
	table := paoRonTable(t, seat(t, 2), seat(t, 1), seat(t, 0))
	table.otherWinner = play.Some(seat(t, 1))

	wins, changes := paoRons(t, table)

	assertEqual(t, "pao", paoSeats(wins), []play.Option[tile.Seat]{{}, play.Some(seat(t, 1))})
	assertEqual(t, "changes by win", scoreChangesByWin(wins), [][tile.SeatCount]int{
		{-5200, 5200, 0, 0}, {-16000, -16000, 32000, 0},
	})
	assertEqual(t, "score changes", changes, [tile.SeatCount]int{-21200, -10800, 32000, 0})
}

func callAndDiscard(t *testing.T, g game.Game, call play.Action, discard tile.TileID) game.Game {
	t.Helper()
	g, _ = discardDrawn(t, g, 1)
	g, _ = script(t, g, act(seat(t, 0), call), act(seat(t, 0), play.DiscardAction(discard)))
	return g
}

func discardDrawnUntilTurnOf(t *testing.T, g game.Game, s tile.Seat) game.Game {
	t.Helper()
	for turnSeat(t, g) != s {
		g, _ = discardDrawn(t, g, 1)
	}
	return g
}

func tsumoAfterGoAround(t *testing.T, g game.Game) play.WinResult {
	t.Helper()
	_, events := script(t, discardDrawnUntilTurnOf(t, g, seat(t, 0)), act(seat(t, 0), play.TsumoAction()))
	return firstWin(t, events)
}

func assertDaisangenPao(t *testing.T, win play.WinResult, want play.Option[tile.Seat]) {
	t.Helper()
	if !hasYaku(win.Yaku, play.YakuDaisangen) {
		t.Errorf("yaku = %v, want daisangen", win.Yaku)
	}
	assertEqual(t, "pao", win.Pao, want)
}

func TestPao_WhenAClosedDragonKanAndTheThirdDragonPon_ShouldCountTheKanAndMakeTheDiscarderLiable(t *testing.T) {
	haku, rinshan := copies(t, 0, "5555z"), tileOf(t, 0, "4z")
	dealer := slices.Concat(haku, copies(t, 0, "6677z"), tankiOnNineSou(t), copies(t, 0, "1z"))
	draws := slices.Concat(
		[]tile.TileID{tileOf(t, 0, "3z"), tileOf(t, 2, "6z"), tileOf(t, 2, "7z")},
		copies(t, 0, "246m"), []tile.TileID{tileOf(t, 1, "9s")},
	)
	g, _ := script(t, paoDealerGame(t, dealer, draws, []tile.TileID{rinshan}),
		act(seat(t, 0), play.KanAction(play.KanClosed, haku[0])), act(seat(t, 0), play.DiscardAction(rinshan)))
	g = ponAndDiscard(t, g, tileOf(t, 0, "1z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "3z"))

	assertDaisangenPao(t, tsumoAfterGoAround(t, g), play.Some(seat(t, 1)))
}

func TestPao_WhenAnOpenDragonKanAndTheThirdDragonPon_ShouldCountTheKanAndMakeTheDiscarderLiable(t *testing.T) {
	rinshan := tileOf(t, 3, "4z")
	dealer := slices.Concat(copies(t, 0, "5556677z"), tankiOnNineSou(t), copies(t, 0, "12z"))
	draws := dragonDraws(t, []tile.TileID{tileOf(t, 3, "5z"), tileOf(t, 2, "6z"), tileOf(t, 2, "7z")})
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, []tile.TileID{rinshan}), 1)
	g = callAndDiscard(t, g, play.KanAction(play.KanOpen, tileOf(t, 3, "5z")), rinshan)
	g = ponAndDiscard(t, g, tileOf(t, 0, "1z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "2z"))

	assertDaisangenPao(t, tsumoAfterGoAround(t, g), play.Some(seat(t, 1)))
}

func TestPao_WhenAnOpenKanCompletesTheThirdDragon_ShouldMakeTheDiscarderLiable(t *testing.T) {
	rinshan := tileOf(t, 3, "4z")
	dealer := slices.Concat(copies(t, 0, "5566777z"), tankiOnNineSou(t), copies(t, 0, "12z"))
	draws := dragonDraws(t, []tile.TileID{tileOf(t, 2, "5z"), tileOf(t, 2, "6z"), tileOf(t, 3, "7z")})
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, []tile.TileID{rinshan}), 1)
	g = ponAndDiscard(t, g, tileOf(t, 0, "1z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "2z"))
	g = callAndDiscard(t, g, play.KanAction(play.KanOpen, tileOf(t, 3, "7z")), rinshan)

	assertDaisangenPao(t, tsumoAfterGoAround(t, g), play.Some(seat(t, 1)))
}

func TestPao_WhenAClosedKanCompletesTheThirdDragon_ShouldNotBeSet(t *testing.T) {
	chun := copies(t, 0, "7777z")
	dealer := slices.Concat(copies(t, 0, "5566777z"), tankiOnNineSou(t), copies(t, 0, "12z"))
	draws := slices.Concat(
		[]tile.TileID{tileOf(t, 0, "3z"), tileOf(t, 2, "5z"), tileOf(t, 2, "6z")},
		copies(t, 0, "246m"), []tile.TileID{chun[3]},
	)
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, []tile.TileID{tileOf(t, 1, "9s")}), 1)
	g = ponAndDiscard(t, g, tileOf(t, 0, "1z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "2z"))
	g = discardDrawnUntilTurnOf(t, g, seat(t, 0))
	g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanClosed, chun[3])))

	_, events := script(t, g, act(seat(t, 0), play.TsumoAction()))

	assertDaisangenPao(t, firstWin(t, events), play.Option[tile.Seat]{})
}

func TestPao_WhenAnAddedKanAndTheFourthWindPon_ShouldCountTheKanAndMakeTheDiscarderLiable(t *testing.T) {
	east, rinshan, junk := copies(t, 0, "1111z"), tileOf(t, 0, "9m"), copies(t, 0, "2468m")
	dealer := slices.Concat(copies(t, 0, "11223344z"), copies(t, 0, "9s"), copies(t, 0, "567z"), copies(t, 0, "1m"))
	draws := slices.Concat(
		[]tile.TileID{tileOf(t, 0, "8s"), tileOf(t, 2, "1z"), tileOf(t, 2, "2z"), tileOf(t, 2, "3z")},
		[]tile.TileID{junk[0], junk[1], junk[2], east[3]},
		[]tile.TileID{junk[3], tileOf(t, 2, "4z")},
		copies(t, 1, "246m"), []tile.TileID{tileOf(t, 1, "9s")},
	)
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, []tile.TileID{rinshan}), 1)
	g = ponAndDiscard(t, g, tileOf(t, 0, "5z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "6z"))
	g = ponAndDiscard(t, g, tileOf(t, 0, "7z"))
	g, _ = discardDrawn(t, g, 3)
	g, _ = script(t, g, act(seat(t, 0), play.KanAction(play.KanAdded, east[3])), act(seat(t, 0), play.DiscardAction(rinshan)))
	g, _ = discardDrawn(t, g, 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 2)))
	g = ponAndDiscard(t, g, tileOf(t, 0, "1m"))

	win := tsumoAfterGoAround(t, g)

	if !hasYaku(win.Yaku, play.YakuDaisuushii) {
		t.Errorf("yaku = %v, want daisuushii", win.Yaku)
	}
	assertEqual(t, "pao", win.Pao, play.Some(seat(t, 2)))
}

func TestPao_WhenTheFourthSuitedKanIsCalled_ShouldAssignNone(t *testing.T) {
	var manQuads []tile.TileID
	for _, kind := range []string{"1m", "2m", "3m", "4m"} {
		manQuads = append(manQuads, tileOf(t, 3, kind))
	}
	rinshan := copies(t, 0, "5566z")
	dealer := slices.Concat(copies(t, 0, "111222333444m"), copies(t, 0, "9s"))
	draws := slices.Concat([]tile.TileID{tileOf(t, 0, "7z")}, manQuads, copies(t, 1, "777z"), []tile.TileID{tileOf(t, 1, "9s")})
	g, _ := discardDrawn(t, paoDealerGame(t, dealer, draws, rinshan), 1)
	for i, quad := range manQuads {
		g = callAndDiscard(t, g, play.KanAction(play.KanOpen, quad), rinshan[i])
	}

	win := tsumoAfterGoAround(t, g)

	if !hasYaku(win.Yaku, play.YakuSuukantsu) {
		t.Errorf("yaku = %v, want suukantsu", win.Yaku)
	}
	assertEqual(t, "pao", win.Pao, play.Option[tile.Seat]{})
}
