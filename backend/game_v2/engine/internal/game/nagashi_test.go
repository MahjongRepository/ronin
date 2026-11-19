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

func noten(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "2345678m2468p68s")
}

func notenHands(t *testing.T) [tile.SeatCount][]tile.TileID {
	t.Helper()
	return [tile.SeatCount][]tile.TileID{noten(t, 0), noten(t, 1), noten(t, 2), noten(t, 3)}
}

func inSeatOrder(index int) tile.Seat {
	return tile.Seats()[index%tile.SeatCount]
}

type forcedDraw struct {
	at int
	id tile.TileID
}

func nagashiWall(
	t *testing.T, hands [tile.SeatCount][]tile.TileID, forced []forcedDraw, qualifying []tile.Seat,
	seatOfDraw func(int) tile.Seat,
) testkit.StartWall {
	t.Helper()
	w := testkit.StartWall{Hands: hands}
	isForced := func(id tile.TileID) bool {
		return slices.ContainsFunc(forced, func(f forcedDraw) bool { return f.id == id })
	}
	var terminals, simples []tile.TileID
	for _, free := range w.UnplacedTiles() {
		switch {
		case isForced(free):
		case free.Kind().IsTerminalOrHonor():
			terminals = append(terminals, free)
		default:
			simples = append(simples, free)
		}
	}

	pop := func(tiles *[]tile.TileID) tile.TileID {
		if len(*tiles) == 0 {
			t.Fatal("no free tile is left for a draw")
		}
		last := (*tiles)[len(*tiles)-1]
		*tiles = (*tiles)[:len(*tiles)-1]
		return last
	}
	var drawnOnce [tile.SeatCount]bool
	for index := range wall.LiveTilesAtDeal {
		drawer := seatOfDraw(index)
		first := !drawnOnce[drawer.Index()]
		drawnOnce[drawer.Index()] = true
		forcedAt := slices.IndexFunc(forced, func(f forcedDraw) bool { return f.at == index })
		switch {
		case forcedAt >= 0:
			w.Draws = append(w.Draws, forced[forcedAt].id)
		case slices.Contains(qualifying, drawer):
			w.Draws = append(w.Draws, pop(&terminals))
		case first || len(simples) > 0:
			w.Draws = append(w.Draws, pop(&simples))
		default:
			w.Draws = append(w.Draws, pop(&terminals))
		}
	}
	return w
}

func playOut(t *testing.T, g game.Game) []play.Emitted {
	t.Helper()
	var events []play.Emitted
	for g.Phase() == play.PhasePlaying {
		for _, s := range awaitedSeats(g) {
			action, _ := g.DefaultAction(s)
			var batch []play.Emitted
			g, batch = script(t, g, act(s, action))
			events = append(events, batch...)
		}
	}
	return events
}

func exhaustiveDraw(t *testing.T, events []play.Emitted) play.ExhaustiveDraw {
	t.Helper()
	draw, ok := roundResult(t, events).(play.ExhaustiveDraw)
	if !ok {
		t.Fatalf("result = %+v, want an exhaustive draw", roundResult(t, events))
	}
	return draw
}

func nagashiSeats(draw play.ExhaustiveDraw) []tile.Seat {
	seats := make([]tile.Seat, len(draw.Nagashi))
	for i, river := range draw.Nagashi {
		seats[i] = river.Seat
	}
	return seats
}

func playedNagashi(t *testing.T, qualifying []tile.Seat, start play.Option[play.StartPosition]) []play.Emitted {
	t.Helper()
	w := nagashiWall(t, notenHands(t), nil, qualifying, inSeatOrder)
	events := playOut(t, begun(t, w, start))
	return events
}

func TestNagashiMangan_WhenTheDealerQualifies_ShouldCollect4000FromEach(t *testing.T) {
	events := playedNagashi(t, []tile.Seat{seat(t, 0)}, noStart())

	draw := exhaustiveDraw(t, events)
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 0)})
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{12000, -4000, -4000, -4000})
	assertEqual(t, "scores", roundEnded(t, events).Scores, [tile.SeatCount]int{37000, 21000, 21000, 21000})
}

func TestNagashiMangan_WhenANonDealerQualifies_ShouldChargeTheDealer4000AndTheOthers2000(t *testing.T) {
	events := playedNagashi(t, []tile.Seat{seat(t, 1)}, noStart())

	draw := exhaustiveDraw(t, events)
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 1)})
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{-4000, 8000, -2000, -2000})
	assertEqual(t, "scores", roundEnded(t, events).Scores, [tile.SeatCount]int{21000, 33000, 23000, 23000})
}

func TestNagashiMangan_WhenTwoSeatsQualify_ShouldNetThePaymentsToAZeroSum(t *testing.T) {
	events := playedNagashi(t, []tile.Seat{seat(t, 0), seat(t, 2)}, noStart())

	draw := exhaustiveDraw(t, events)
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 0), seat(t, 2)})
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{8000, -6000, 4000, -6000})
}

func TestNagashiMangan_WhenRiichiSticksAreOnTheTable_ShouldLeaveThemThere(t *testing.T) {
	events := playedNagashi(t, []tile.Seat{seat(t, 0)}, eastStart(sticksPaidScores(3), 0, 3))

	ended := roundEnded(t, events)
	assertEqual(t, "scores", ended.Scores, [tile.SeatCount]int{36000, 20000, 20000, 21000})
	assertEqual(t, "riichi sticks", ended.RiichiSticks, 3)
}

func TestNagashiMangan_WhenHonbaIsOnTheTable_ShouldAddNoBonus(t *testing.T) {
	scores := [tile.SeatCount]int{25000, 25000, 25000, 25000}
	events := playedNagashi(t, []tile.Seat{seat(t, 1)}, eastStart(scores, 5, 0))

	draw := exhaustiveDraw(t, events)
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 1)})
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{-4000, 8000, -2000, -2000})
}

func TestNagashiMangan_WhenASimpleIsDiscarded_ShouldNotQualify(t *testing.T) {
	simple := forcedDraw{0, tileOf(t, 0, "5p")}
	w := nagashiWall(t, notenHands(t), []forcedDraw{simple}, []tile.Seat{seat(t, 0), seat(t, 2)}, inSeatOrder)

	events := playOut(t, begun(t, w, noStart()))

	assertEqual(t, "nagashi", nagashiSeats(exhaustiveDraw(t, events)), []tile.Seat{seat(t, 2)})
}

func TestNagashiMangan_WhenADiscardWasClaimed_ShouldNotQualify(t *testing.T) {
	claimedEast := forcedDraw{0, tileOf(t, 2, "1z")}
	hands := notenHands(t)
	hands[1] = slices.Concat(copies(t, 1, "2345678m2468p"), copies(t, 0, "11z"))
	dealerFirst := func(index int) tile.Seat {
		if index == 0 {
			return seat(t, 0)
		}
		return inSeatOrder(index + 1)
	}
	w := nagashiWall(t, hands, []forcedDraw{claimedEast}, []tile.Seat{seat(t, 0), seat(t, 2)}, dealerFirst)
	g, _ := discardDrawn(t, begun(t, w, noStart()), 1)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 1)))
	g, _ = script(t, g, act(seat(t, 1), firstPon(t, g, seat(t, 1))), act(seat(t, 1), play.DiscardAction(tileOf(t, 1, "8p"))))

	events := playOut(t, g)

	assertEqual(t, "nagashi", nagashiSeats(exhaustiveDraw(t, events)), []tile.Seat{seat(t, 2)})
}

func TestNagashiMangan_WhenTheSeatCalledAnothersTile_ShouldStillQualify(t *testing.T) {
	nineMan := tileOf(t, 0, "9m")
	hands := notenHands(t)
	hands[0] = slices.Concat(copies(t, 0, "2345678m246p"), copies(t, 0, "11z"), []tile.TileID{nineMan})
	forced := []forcedDraw{{1, tileOf(t, 0, "2s")}, {2, tileOf(t, 1, "2s")}, {3, tileOf(t, 2, "1z")}}
	firstGoAroundThenFromSeatOne := func(index int) tile.Seat {
		if index < tile.SeatCount {
			return inSeatOrder(index)
		}
		return inSeatOrder(index + 1)
	}
	w := nagashiWall(t, hands, forced, []tile.Seat{seat(t, 0)}, firstGoAroundThenFromSeatOne)
	g, _ := discardDrawn(t, begun(t, w, noStart()), tile.SeatCount)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingCall(seat(t, 0)))
	g, _ = script(t, g, act(seat(t, 0), firstPon(t, g, seat(t, 0))), act(seat(t, 0), play.DiscardAction(nineMan)))

	events := playOut(t, g)

	draw := exhaustiveDraw(t, events)
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 0)})
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{12000, -4000, -4000, -4000})
}

func seatOneDealsAfterSeatZeroTenpaiOnSevenSou(t *testing.T) (testkit.StartWall, play.Option[play.StartPosition]) {
	t.Helper()
	hands := notenHands(t)
	hands[0] = copies(t, 0, "234567m234p5568s")
	fromSeatOne := func(index int) tile.Seat { return inSeatOrder(index + 1) }
	w := nagashiWall(t, hands, nil, []tile.Seat{seat(t, 0)}, fromSeatOne)
	start := testkit.EastStart([tile.SeatCount]int{25000, 25000, 25000, 25000}, 0, 0)
	start.Dealer, start.RoundNumber = seat(t, 1), 1
	return w, play.Some(start)
}

func TestExhaustiveDraw_WhenOnlyTerminalAndHonorDiscards_ShouldPayNagashiManganOverNotenPayments(t *testing.T) {
	w, start := seatOneDealsAfterSeatZeroTenpaiOnSevenSou(t)

	events := playOut(t, begun(t, w, start))

	draw := exhaustiveDraw(t, events)
	if len(draw.Tenpai) != 1 || draw.Tenpai[0].Seat != seat(t, 0) {
		t.Fatalf("tenpai = %+v, want seat 0 alone", draw.Tenpai)
	}
	assertEqual(t, "tenpai hand", draw.Tenpai[0].Hand, copies(t, 0, "234567m234p5568s"))
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 0)})
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{8000, -4000, -2000, -2000})
	assertEqual(t, "seat 0 score", roundEnded(t, events).Scores[0], 33000)
}

func discardsOf(events []play.Emitted, discarder tile.Seat) []play.RiverTile {
	var river []play.RiverTile
	for _, emitted := range events {
		if d, ok := emitted.Event.(play.Discarded); ok && d.Seat == discarder {
			river = append(river, play.RiverTile{Tile: d.Tile, Tsumogiri: d.Tsumogiri, Riichi: d.Riichi})
		}
	}
	return river
}

func TestExhaustiveDraw_WhenTheNagashiManganSeatDeclaredRiichi_ShouldShowItsRiverAsItFell(t *testing.T) {
	w, start := seatOneDealsAfterSeatZeroTenpaiOnSevenSou(t)
	g := begun(t, w, start)
	var events []play.Emitted
	for s, ok := testkit.TurnSeat(g); !ok || s != seat(t, 0); s, ok = testkit.TurnSeat(g) {
		if len(awaitedSeats(g)) == 0 {
			t.Fatal("the round ended before seat 0's turn")
		}
		for _, s := range awaitedSeats(g) {
			action, _ := g.DefaultAction(s)
			var batch []play.Emitted
			g, batch = script(t, g, act(s, action))
			events = append(events, batch...)
		}
	}
	riichiDiscard, ok := testkit.Drawn(g)
	if !ok {
		t.Fatal("seat 0's turn follows no draw")
	}
	g, declared := script(t, g, act(seat(t, 0), play.RiichiAction(riichiDiscard)))
	events = append(events, declared...)

	rest := playOut(t, g)
	events = append(events, rest...)

	draw := exhaustiveDraw(t, events)
	assertEqual(t, "nagashi", nagashiSeats(draw), []tile.Seat{seat(t, 0)})
	river := draw.Nagashi[0].River
	assertEqual(t, "river", river, discardsOf(events, seat(t, 0)))
	assertEqual(t, "riichi discard", river[0], play.RiverTile{Tile: riichiDiscard, Tsumogiri: true, Riichi: true})
	if len(river) < 2 {
		t.Fatalf("river = %+v, want discards after the riichi", river)
	}
	for _, discard := range river[1:] {
		if !discard.Tsumogiri || discard.Riichi {
			t.Errorf("discard after the riichi = %+v, want a plain tsumogiri", discard)
		}
	}
	assertEqual(t, "seat 0 score", roundEnded(t, events).Scores[0], 32000)
}
