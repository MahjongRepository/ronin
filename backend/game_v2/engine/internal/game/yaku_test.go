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

func winOf(t *testing.T, g game.Game, s tile.Seat, action play.Action) play.WinResult {
	t.Helper()
	_, events := script(t, g, act(s, action))
	return firstWin(t, events)
}

func quietDora(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 3, "9p")
}

func winningDealtHand(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "123456789m1235p")
}

func manPin(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789m1234p")
}

func manPinBystanders(t *testing.T, first []tile.TileID) [tile.SeatCount][]tile.TileID {
	t.Helper()
	return [tile.SeatCount][]tile.TileID{first, manPin(t, 1), manPin(t, 2), manPin(t, 3)}
}

func TestTenhou_WhenTheDealerTsumosOnTheDealtHand_ShouldScoreTenhouNotChiihou(t *testing.T) {
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			winningDealtHand(t), souWithWinds(t, 1), souWithWinds(t, 2), souWithWinds(t, 3),
		},
		Draws: copies(t, 1, "5p"),
	}

	win := winOf(t, begun(t, w, noStart()), seat(t, 0), play.TsumoAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTenhou})
}

func TestChiihou_WhenANonDealerTsumosOnItsFirstDrawAfterTheDealersDiscard_ShouldScoreChiihouNotTenhou(t *testing.T) {
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			souWithWinds(t, 0), copies(t, 0, "123456789m1255p"), souWithWinds(t, 2), souWithWinds(t, 3),
		},
		Draws: slices.Concat(copies(t, 0, "5z"), copies(t, 0, "3p")),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))

	win := winOf(t, g, seat(t, 1), play.TsumoAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuChiihou})
}

func TestTenhou_WhenDiscardsWereMade_ShouldNotBeScored(t *testing.T) {
	g := goAroundGame(t, manPinBystanders(t, winningDealtHand(t)), copies(t, 1, "5p"), noStart(), quietDora(t))

	win := winOf(t, g, seat(t, 0), play.TsumoAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuIttsu})
}

func TestChiihou_WhenTheSeatAlreadyDiscarded_ShouldNotBeScored(t *testing.T) {
	hands := [tile.SeatCount][]tile.TileID{manPin(t, 1), copies(t, 0, "123456789m1255p"), manPin(t, 2), manPin(t, 3)}
	g := goAroundGame(t, hands, slices.Concat(copies(t, 0, "1z"), copies(t, 0, "3p")), noStart(), quietDora(t))
	g, _ = discardDrawn(t, g, 1)

	win := winOf(t, g, seat(t, 1), play.TsumoAction())

	if hasYaku(win.Yaku, play.YakuChiihou) {
		t.Errorf("yaku = %v, want no chiihou", win.Yaku)
	}
}

func ittsuEastTanki(t *testing.T) []tile.TileID {
	t.Helper()
	return copies(t, 0, "123456789m444p1z")
}

func playedToTheLastDraw(t *testing.T, hands [tile.SeatCount][]tile.TileID, rinshan []tile.TileID) game.Game {
	t.Helper()
	lastEast := tileOf(t, 1, "1z")
	w := testkit.StartWall{
		Hands:   hands,
		Rinshan: rinshan,
		Dora:    play.Some(quietDora(t)),
		Ura:     []tile.TileID{doraFreeUra(t)},
	}
	var fillers []tile.TileID
	for _, free := range w.UnplacedTiles() {
		if free != lastEast && len(fillers) < wall.LiveTilesAtDeal-1 {
			fillers = append(fillers, free)
		}
	}
	w.Draws = slices.Concat(fillers, []tile.TileID{lastEast})
	g := playDefaultsWhileLiveTilesExceed(t, begun(t, w, noStart()), 0)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	if hand := g.Hand(seat(t, 1)); hand[len(hand)-1] != lastEast {
		t.Fatalf("last drawn tile = %v, want the last East", hand[len(hand)-1])
	}
	return g
}

func TestHaitei_WhenTheTsumoIsOnTheLastTile_ShouldAwardHaiteiNotHoutei(t *testing.T) {
	hands := [tile.SeatCount][]tile.TileID{
		copies(t, 1, "123456789s2345z"), ittsuEastTanki(t), copies(t, 2, "123456789s2345z"), copies(t, 3, "123456789s2345z"),
	}
	g := playedToTheLastDraw(t, hands, copies(t, 2, "11z"))

	win := winOf(t, g, seat(t, 1), play.TsumoAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuHaitei, play.YakuIttsu})
	assertEqual(t, "aka dora", win.Dora.AkaDora, 1)
}

func TestHoutei_WhenTheRonIsOnTheLastDiscard_ShouldAwardHouteiNotHaitei(t *testing.T) {
	hands := [tile.SeatCount][]tile.TileID{
		slices.Concat(copies(t, 1, "123456789s234z"), copies(t, 2, "1z")),
		slices.Concat(copies(t, 2, "123456789s234z"), copies(t, 2, "9p")),
		ittsuEastTanki(t),
		slices.Concat(copies(t, 3, "123456789s234z"), copies(t, 3, "1z")),
	}
	g := playedToTheLastDraw(t, hands, nil)
	g, _ = script(t, g, act(seat(t, 1), play.DiscardAction(tileOf(t, 1, "1z"))))
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 2)))
	decision, _ := g.Decision(seat(t, 2))
	if call, ok := decision.Context.(play.Call); !ok || !call.Houtei {
		t.Fatalf("seat 2's decision = %+v, want a houtei call prompt", decision.Context)
	}

	win := winOf(t, g, seat(t, 2), play.RonAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuHoutei, play.YakuIttsu})
	assertEqual(t, "aka dora", win.Dora.AkaDora, 1)
}

func TestRyuuiisou_WhenAnAllGreenHandWinsByTsumo_ShouldStackWithSuuankouTankiAsSingleYakuman(t *testing.T) {
	for _, c := range []struct {
		hand    []tile.TileID
		winTile tile.TileID
	}{
		{slices.Concat(copies(t, 0, "2223334446s"), copies(t, 1, "666z")), tileOf(t, 1, "6s")},
		{copies(t, 0, "2223334446668s"), tileOf(t, 1, "8s")},
	} {
		g := goAroundGame(t, manPinBystanders(t, c.hand), []tile.TileID{c.winTile}, noStart(), quietDora(t))

		win := winOf(t, g, seat(t, 0), play.TsumoAction())

		assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuRyuuiisou, play.YakuSuuankouTanki})
		assertEqual(t, "yakuman", yakumanCount(win.Value), 2)
	}
}

func TestDoubleRiichi_WhenTheRiichiDealerTsumos_ShouldScoreTheRiichiItsDiscardMade(t *testing.T) {
	for _, c := range []struct {
		riichiGoAround int
		riichiYaku     play.YakuID
	}{
		{0, play.YakuDaburuRiichi},
		{1, play.YakuRiichi},
	} {
		goArounds := [][]tile.TileID{copies(t, 0, "1234z"), copies(t, 1, "1234z"), copies(t, 2, "1234z")}
		w := testkit.StartWall{
			Hands: manPinBystanders(t, winningDealtHand(t)),
			Draws: slices.Concat(slices.Concat(goArounds[:c.riichiGoAround+2]...), copies(t, 1, "5p")),
			Dora:  play.Some(quietDora(t)),
			Ura:   []tile.TileID{doraFreeUra(t)},
		}
		g, _ := discardDrawn(t, begun(t, w, noStart()), tile.SeatCount*c.riichiGoAround)
		g, _ = script(t, g, act(seat(t, 0), play.RiichiAction(goArounds[c.riichiGoAround][0])))
		g, _ = discardDrawn(t, g, 7)

		win := winOf(t, g, seat(t, 0), play.TsumoAction())

		var riichi []play.YakuID
		for _, yaku := range win.Yaku {
			if yaku == play.YakuRiichi || yaku == play.YakuDaburuRiichi || yaku == play.YakuIppatsu {
				riichi = append(riichi, yaku)
			}
		}
		assertEqual(t, "riichi yaku", riichi, []play.YakuID{c.riichiYaku})
	}
}

func seatOneTsumoAfterAGoAround(t *testing.T, hand []tile.TileID, winTile, dora tile.TileID) play.WinResult {
	t.Helper()
	honorsFree := func(first int) []tile.TileID { return copies(t, first, "2468m2468p2468s1z") }
	hands := [tile.SeatCount][]tile.TileID{honorsFree(0), hand, honorsFree(1), honorsFree(2)}
	g := goAroundGame(t, hands, []tile.TileID{tileOf(t, 3, "1z"), winTile}, noStart(), dora)
	g, _ = discardDrawn(t, g, 1)
	return winOf(t, g, seat(t, 1), play.TsumoAction())
}

func TestSuuankouTanki_ShouldCountAsASingleYakuman(t *testing.T) {
	win := seatOneTsumoAfterAGoAround(t, copies(t, 0, "111m333p5557779s"), tileOf(t, 1, "9s"), quietDora(t))

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuSuuankouTanki})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 1)
	assertEqual(t, "limit", win.Limit, play.Some(play.LimitYakuman))
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{-16000, 32000, -8000, -8000})
}

func TestSuuankou_WhenTheWaitIsNotTanki_ShouldBeASingleYakuman(t *testing.T) {
	win := seatOneTsumoAfterAGoAround(t, copies(t, 0, "11m333p55577799s"), tileOf(t, 2, "1m"), quietDora(t))

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuSuuankou})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 1)
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{-16000, 32000, -8000, -8000})
}

func TestYakumanHand_WhenItHoldsDora_ShouldAddNoHanAndCountNoDora(t *testing.T) {
	win := seatOneTsumoAfterAGoAround(t, copies(t, 0, "111m333p5557779s"), tileOf(t, 1, "9s"), tileOf(t, 3, "9m"))

	assertEqual(t, "yakuman", yakumanCount(win.Value), 1)
	assertEqual(t, "dora", win.Dora, play.DoraCount{})
}

func pinsForManHands(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "123456789p1359s")
}

func seatOneRiichiThenTsumo(t *testing.T, hand []tile.TileID, winTile, dora tile.TileID) play.WinResult {
	t.Helper()
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{pinsForManHands(t, 0), hand, pinsForManHands(t, 1), pinsForManHands(t, 2)},
		Draws: slices.Concat(
			copies(t, 0, "1234z"), copies(t, 1, "1234z"), copies(t, 2, "1234z"), copies(t, 3, "1z"), []tile.TileID{winTile},
		),
		Dora: play.Some(dora),
		Ura:  []tile.TileID{doraFreeUra(t)},
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 5)
	g, _ = script(t, g, act(seat(t, 1), play.RiichiAction(tileOf(t, 1, "2z"))))
	g, _ = discardDrawn(t, g, 7)
	return winOf(t, g, seat(t, 1), play.TsumoAction())
}

func TestKazoeYakuman_WhenDoraLiftTheHanTo13_ShouldScoreYakuman(t *testing.T) {
	chinitsuWithoutRedFive := slices.Concat(copies(t, 0, "223344m"), copies(t, 1, "555m"), copies(t, 0, "6677m"))
	eightMan := tileOf(t, 0, "8m")

	withoutDora := seatOneRiichiThenTsumo(t, chinitsuWithoutRedFive, eightMan, tileOf(t, 3, "1p"))
	withDora := seatOneRiichiThenTsumo(t, chinitsuWithoutRedFive, eightMan, tileOf(t, 3, "4m"))

	if han, ok := withoutDora.Value.(play.Han); !ok || han.Han != 11 {
		t.Errorf("value without dora = %v, want 11 han", withoutDora.Value)
	}
	assertEqual(t, "limit without dora", withoutDora.Limit, play.Some(play.LimitSanbaiman))
	assertEqual(t, "dealer payment without dora", withoutDora.ScoreChanges[0], -12000)
	if han, ok := withDora.Value.(play.Han); !ok || han.Han < 13 {
		t.Errorf("value with dora = %v, want 13 han or more", withDora.Value)
	}
	assertEqual(t, "limit with dora", withDora.Limit, play.Some(play.LimitYakuman))
	assertEqual(t, "dealer payment with dora", withDora.ScoreChanges[0], -16000)
	if slices.ContainsFunc(withDora.Yaku, play.YakuID.IsYakuman) {
		t.Errorf("yaku = %v, want no yakuman yaku", withDora.Yaku)
	}
}

func TestNonYakumanHand_WhenItHoldsDora_ShouldCountThem(t *testing.T) {
	hand := slices.Concat(copies(t, 0, "123456789m"), copies(t, 1, "2355m"))

	win := seatOneRiichiThenTsumo(t, hand, tileOf(t, 1, "4m"), tileOf(t, 3, "4m"))

	assertEqual(t, "dora", win.Dora.Dora, 3)
}

func TestChiihou_WhenAMeldWasMade_ShouldNotBeScored(t *testing.T) {
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			souWithWinds(t, 0),
			copies(t, 0, "123456789m1255p"),
			slices.Concat(copies(t, 1, "55z"), copies(t, 1, "123456789s"), copies(t, 1, "12z")),
			souWithWinds(t, 3),
		},
		Draws: slices.Concat(copies(t, 0, "5z"), copies(t, 0, "66z"), copies(t, 0, "3p")),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	g, _ = script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))), act(seat(t, 2), play.DiscardAction(tileOf(t, 1, "1z"))))
	g, _ = discardDrawn(t, g, 2)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))

	win := winOf(t, g, seat(t, 1), play.TsumoAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsumo, play.YakuIttsu})
}

func TestRyuuiisou_WhenAnOpenHatsuPonWinsByTsumo_ShouldScoreYakuman(t *testing.T) {
	extra, hatsuFromSeatThree := tileOf(t, 0, "7z"), tileOf(t, 0, "6z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(copies(t, 1, "66z"), copies(t, 0, "2223334448s"), []tile.TileID{extra}),
			manPin(t, 1),
			manPin(t, 2),
			slices.Concat(copies(t, 3, "123456789m123p"), []tile.TileID{hatsuFromSeatThree}),
		},
		Draws: slices.Concat(copies(t, 0, "1234z"), copies(t, 0, "555z"), copies(t, 1, "8s")),
		Dora:  play.Some(quietDora(t)),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 3)
	g, _ = script(t, g, act(seat(t, 3), play.DiscardAction(hatsuFromSeatThree)))
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(extra)))
	g, _ = discardDrawn(t, g, 3)

	win := winOf(t, g, seat(t, 0), play.TsumoAction())

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuRyuuiisou})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 1)
}

func eastPonThenRonOnThePair(t *testing.T, pair string) play.WinResult {
	t.Helper()
	extra := tileOf(t, 0, "7z")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			pinsForManHands(t, 1),
			slices.Concat(copies(t, 0, "11z"), copies(t, 0, "222333444z"), copies(t, 0, pair), []tile.TileID{extra}),
			pinsForManHands(t, 2),
			pinsForManHands(t, 3),
		},
		Draws: slices.Concat(copies(t, 2, "1z"), copies(t, 1, pair)),
		Dora:  play.Some(tileOf(t, 0, "9m")),
	}
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	g, _ = script(t, g, act(seat(t, 1), firstPon(t, g, seat(t, 1))), act(seat(t, 1), play.DiscardAction(extra)))
	g, _ = discardDrawn(t, g, 1)
	return winOf(t, g, seat(t, 1), play.RonAction())
}

func TestDaisuushii_WhenTheEastPonIsOpen_ShouldCountAsASingleYakuman(t *testing.T) {
	win := eastPonThenRonOnThePair(t, "1m")

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuDaisuushii})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 1)
	assertEqual(t, "pao", win.Pao, play.Option[tile.Seat]{})
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{0, 32000, -32000, 0})
}

func TestYakumanStacking_WhenDaisuushiiAndTsuuiisou_ShouldStackTwoSingleYakuman(t *testing.T) {
	win := eastPonThenRonOnThePair(t, "5z")

	assertEqual(t, "yaku", win.Yaku, []play.YakuID{play.YakuTsuuiisou, play.YakuDaisuushii})
	assertEqual(t, "yakuman", yakumanCount(win.Value), 2)
	assertEqual(t, "score changes", win.ScoreChanges, [tile.SeatCount]int{0, 64000, -64000, 0})
}

func TestIppatsu_WhenACallComesBeforeTheRon_ShouldEndIt(t *testing.T) {
	riichiDiscard, calledHaku, oneMan := tileOf(t, 1, "7z"), tileOf(t, 0, "5z"), tileOf(t, 2, "1m")
	w := testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			tenpaiOnOneAndNineMan(t),
			copies(t, 1, "123456789p159s5z"),
			slices.Concat(copies(t, 2, "123456789p19s"), copies(t, 2, "55z")),
			slices.Concat(copies(t, 3, "123456789p159s"), copies(t, 0, "6z")),
		},
		Draws: []tile.TileID{riichiDiscard, calledHaku, oneMan},
	}
	g, _ := script(t, begun(t, w, noStart()), act(seat(t, 0), play.RiichiAction(riichiDiscard)))
	g, _ = discardDrawn(t, g, 1)
	g, _ = script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))), act(seat(t, 2), play.DiscardAction(tileOf(t, 2, "9s"))))
	g, _ = discardDrawn(t, g, 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))

	win := winOf(t, g, seat(t, 0), play.RonAction())

	if !hasYaku(win.Yaku, play.YakuDaburuRiichi) || hasYaku(win.Yaku, play.YakuIppatsu) {
		t.Errorf("yaku = %v, want daburu riichi without ippatsu", win.Yaku)
	}
}
