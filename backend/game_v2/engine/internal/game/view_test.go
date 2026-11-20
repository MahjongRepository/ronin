package game_test

import (
	"cmp"
	"reflect"
	"slices"
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func publicPart(view play.SeatView) play.SeatRecord {
	public := view.Record
	public.Seat = tile.Seats()[0]
	public.Hand = nil
	public.Drawn = play.Option[tile.TileID]{}
	public.Furiten = false
	return public
}

func assertPublicPartsAgree(t *testing.T, g game.Game) {
	t.Helper()
	first := publicPart(g.SeatView(seat(t, 0)))
	seats := tile.Seats()
	for _, s := range seats[1:] {
		assertEqual(t, "public part of seat "+strconv.Itoa(s.Index()), publicPart(g.SeatView(s)), first)
	}
}

type seatDiscard struct {
	seat    tile.Seat
	discard play.RiverTile
}

func discardedTiles(events []play.Emitted) []seatDiscard {
	var discards []seatDiscard
	for _, e := range events {
		if d, ok := e.Event.(play.Discarded); ok {
			discards = append(discards, seatDiscard{d.Seat, play.RiverTile{Tile: d.Tile, Tsumogiri: d.Tsumogiri, Riichi: d.Riichi}})
		}
	}
	return discards
}

func hakuRiichiWall(t *testing.T) testkit.StartWall {
	t.Helper()
	return testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m123p9s"),
			junk(t, 1),
			slices.Concat(copies(t, 2, "1357m2468p135s"), copies(t, 0, "55z")),
			junk(t, 3),
		},
		Draws: []tile.TileID{
			tileOf(t, 0, "1z"), tileOf(t, 0, "2z"), tileOf(t, 0, "3z"), tileOf(t, 0, "4z"), tileOf(t, 2, "5z"),
		},
	}
}

func dealerRiichiOnHaku(t *testing.T) (game.Game, []play.Emitted) {
	t.Helper()
	g, events := script(t, begun(t, hakuRiichiWall(t), noStart()), act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "9s"))))
	g, drawn := discardDrawn(t, g, 3)
	g, riichi := script(t, g, act(seat(t, 0), play.RiichiAction(tileOf(t, 2, "5z"))))
	return g, slices.Concat(events, drawn, riichi)
}

func kyuushuWall(t *testing.T) [tile.TileIDCount]tile.TileID {
	t.Helper()
	w := testkit.StartWall{Hands: [tile.SeatCount][]tile.TileID{copies(t, 0, "19m19p19s1234567z")}}
	return wallTiles(t, w, seat(t, 0))
}

func TestSeatView_ShouldShowOnlyTheSeatsOwnHandAndDecision(t *testing.T) {
	g, _ := script(t, threePinWithTwoRonCallers(t), act(seat(t, 3), play.RonAction()))

	for _, s := range tile.Seats() {
		view := g.SeatView(s)
		assertEqual(t, "seat", view.Record.Seat, s)
		assertEqual(t, "hand", view.Record.Hand, g.Hand(s))
		assertEqual(t, "closed tiles", view.Record.Players[s.Index()].ClosedTiles, len(g.Hand(s)))
	}

	caller := g.SeatView(seat(t, 0))
	decision, awaited := g.Decision(seat(t, 0))
	assertEqual(t, "caller's decision", caller.Decision, play.Option[play.Decision]{Value: decision, OK: awaited})
	if _, isCall := caller.Decision.Value.Context.(play.Call); !caller.Decision.OK || !isCall {
		t.Errorf("caller's decision = %+v, want a call prompt", caller.Decision)
	}
	assertEqual(t, "caller's drawn tile", caller.Record.Drawn, play.Option[tile.TileID]{})
	assertEqual(t, "answered seat's decision", g.SeatView(seat(t, 3)).Decision.OK, false)
	assertPublicPartsAgree(t, g)
}

func TestSeatView_ShouldShowOnlyTheSeatsOwnFuriten(t *testing.T) {
	g, _ := script(t, threePinWithTwoRonCallers(t), act(seat(t, 0), play.PassAction()))

	assertEqual(t, "passed seat's furiten", g.SeatView(seat(t, 0)).Record.Furiten, true)
	assertEqual(t, "other caller's furiten", g.SeatView(seat(t, 3)).Record.Furiten, false)
	assertEqual(t, "other caller's decision", g.SeatView(seat(t, 3)).Decision.OK, true)
	assertEqual(t, "passed seat's decision", g.SeatView(seat(t, 0)).Decision.OK, false)
	assertPublicPartsAgree(t, g)
}

func TestSeatView_ShouldShowTheDrawnTileOnlyToTheSeatOnItsTurn(t *testing.T) {
	g := begun(t, hakuRiichiWall(t), noStart())

	assertEqual(t, "dealer's drawn tile", g.SeatView(seat(t, 0)).Record.Drawn, play.Some(tileOf(t, 0, "1z")))
	assertEqual(t, "other seat's drawn tile", g.SeatView(seat(t, 1)).Record.Drawn, play.Option[tile.TileID]{})
	assertEqual(t, "latest discard", g.SeatView(seat(t, 0)).Record.LatestDiscard, play.Option[tile.Seat]{})

	g, _ = script(t, g, act(seat(t, 0), play.DiscardAction(tileOf(t, 0, "9s"))))

	assertEqual(t, "dealer's drawn tile after its discard", g.SeatView(seat(t, 0)).Record.Drawn, play.Option[tile.TileID]{})
	assertEqual(t, "next seat's drawn tile", g.SeatView(seat(t, 1)).Record.Drawn, play.Some(tileOf(t, 0, "2z")))
}

func TestSeatView_ShouldKeepHowEachDiscardFellInTheRivers(t *testing.T) {
	g, events := dealerRiichiOnHaku(t)
	g, called := script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))), act(seat(t, 2), play.DiscardAction(tileOf(t, 2, "1m"))))
	events = append(events, called...)

	view := g.SeatView(seat(t, 1))
	var rivers [tile.SeatCount][]play.RiverTile
	for i, player := range view.Record.Players {
		rivers[i] = player.River
	}
	river := func(first int, mpsz string, tsumogiri, riichi bool) play.RiverTile {
		return play.RiverTile{Tile: tileOf(t, first, mpsz), Tsumogiri: tsumogiri, Riichi: riichi}
	}
	assertEqual(t, "rivers", rivers, [tile.SeatCount][]play.RiverTile{
		{river(0, "9s", false, false), river(2, "5z", true, true)},
		{river(0, "2z", true, false)},
		{river(0, "3z", true, false), river(2, "1m", false, false)},
		{river(0, "4z", true, false)},
	})
	fromEvents := discardedTiles(events)
	slices.SortStableFunc(fromEvents, func(a, b seatDiscard) int { return cmp.Compare(a.seat.Index(), b.seat.Index()) })
	var fromRivers []seatDiscard
	for _, s := range tile.Seats() {
		for _, discard := range rivers[s.Index()] {
			fromRivers = append(fromRivers, seatDiscard{s, discard})
		}
	}
	assertEqual(t, "discards", fromRivers, fromEvents)

	pon := view.Record.Players[2].Melds[0]
	assertEqual(t, "pon kind", pon.Kind, play.MeldPon)
	assertEqual(t, "pon's called tile", pon.Called, play.Some(tileOf(t, 2, "5z")))
	assertEqual(t, "pon's discarder", pon.From, play.Some(seat(t, 0)))
	assertEqual(t, "ponning seat's closed tiles", view.Record.Players[2].ClosedTiles, 10)
	assertEqual(t, "dealer's riichi", view.Record.Players[0].Riichi.OK, true)
	assertEqual(t, "dealer's score", view.Record.Players[0].Score, 24000)
	assertEqual(t, "sticks", view.Record.RiichiSticks, 1)
}

func TestSeatViewLatestDiscard_ShouldLastUntilACallOrTheNextDraw(t *testing.T) {
	g, _ := dealerRiichiOnHaku(t)
	assertEqual(t, "latest discard", g.SeatView(seat(t, 1)).Record.LatestDiscard, play.Some(seat(t, 0)))
	assertEqual(t, "riichi before the ron window closes", g.SeatView(seat(t, 1)).Record.Players[0].Riichi.OK, false)

	passed, _ := script(t, g, act(seat(t, 2), play.PassAction()))
	view := passed.SeatView(seat(t, 1))
	assertEqual(t, "latest discard after the next draw", view.Record.LatestDiscard, play.Option[tile.Seat]{})
	assertEqual(t, "current after the next draw", view.Record.Current, seat(t, 1))
	assertEqual(t, "riichi after the next draw", view.Record.Players[0].Riichi.OK, true)

	ponned, _ := script(t, g, act(seat(t, 2), firstPon(t, g, seat(t, 2))))
	assertEqual(t, "latest discard after a pon", ponned.SeatView(seat(t, 1)).Record.LatestDiscard, play.Option[tile.Seat]{})
	assertEqual(t, "current after a pon", ponned.SeatView(seat(t, 1)).Record.Current, seat(t, 2))
}

func TestSeatView_WhenARonEndsTheRound_ShouldShowTheEndedRoundAndItsResult(t *testing.T) {
	g := threePinWithTwoRonCallers(t)
	header := g.Header()
	assertEqual(t, "result in play", g.SeatView(seat(t, 1)).Record.Result, nil)
	assertEqual(t, "history in play", g.SeatView(seat(t, 1)).Record.History, nil)

	g, events := script(t, g, act(seat(t, 0), play.RonAction()), act(seat(t, 3), play.RonAction()))

	result := roundResult(t, events)
	view := g.SeatView(seat(t, 1))
	assertEqual(t, "phase", view.Record.Phase, play.PhaseRoundOver)
	assertEqual(t, "header", view.Record.Header, header)
	assertEqual(t, "result", view.Record.Result, result)
	assertEqual(t, "latest discard", view.Record.LatestDiscard, play.Some(seat(t, 2)))
	assertEqual(t, "decision", view.Decision.OK, false)
	var scores [tile.SeatCount]int
	for i, player := range view.Record.Players {
		scores[i] = player.Score
	}
	assertEqual(t, "scores", scores, g.Scores())
	assertEqual(t, "history", view.Record.History, []play.FinishedRound{{Header: header, Result: result}})
}

func TestSeatViewHistory_ShouldHoldEveryFinishedRoundWithItsHeader(t *testing.T) {
	g, _ := newGame(t, fixed(kyuushuWall(t), kyuushuWall(t)), noStart())

	first := g.Header()
	g, _ = script(t, g, act(seat(t, 0), play.KyuushuAction()))
	aborted := play.Abortive{Kind: play.KyuushuKyuuhai{Seat: seat(t, 0), Hand: g.Hand(seat(t, 0))}}
	g = dealNextRound(t, g)

	dealt := g.SeatView(seat(t, 2))
	assertEqual(t, "phase", dealt.Record.Phase, play.PhasePlaying)
	assertEqual(t, "result", dealt.Record.Result, nil)
	assertEqual(t, "round number", dealt.Record.Header.RoundNumber, 1)
	assertEqual(t, "honba", dealt.Record.Header.Honba, 1)
	assertEqual(t, "first dealer", dealt.Record.FirstDealer, seat(t, 0))
	ones := tile.Dice{First: 1, Second: 1}
	assertEqual(t, "first dealer dice", dealt.Record.FirstDealerDice, [2]tile.Dice{ones, ones})

	second := g.Header()
	g, _ = script(t, g, act(seat(t, 0), play.KyuushuAction()))

	view := g.SeatView(seat(t, 2))
	assertEqual(t, "header", view.Record.Header, second)
	assertEqual[play.RoundResult](t, "result", view.Record.Result, aborted)
	assertEqual(t, "history", view.Record.History, []play.FinishedRound{
		{Header: first, Result: aborted},
		{Header: second, Result: aborted},
	})
}

func TestSeatView_WhenTheLiveWallRunsOut_ShouldKeepTheLastDiscard(t *testing.T) {
	g, _ := newGame(t, seededBy(t, "ab"), noStart())
	var lastDiscarder play.Option[tile.Seat]
	for g.Phase() == play.PhasePlaying {
		for _, s := range awaitedSeats(g) {
			action, _ := g.DefaultAction(s)
			var events []play.Emitted
			g, events = script(t, g, act(s, action))
			if discards := discardedTiles(events); len(discards) > 0 {
				lastDiscarder = play.Some(discards[len(discards)-1].seat)
			}
		}
	}

	view := g.SeatView(seat(t, 0))
	if _, exhaustive := view.Record.Result.(play.ExhaustiveDraw); !exhaustive {
		t.Errorf("result = %+v, want an exhaustive draw", view.Record.Result)
	}
	assertEqual(t, "live tiles", view.Record.LiveTiles, 0)
	assertEqual(t, "latest discard", view.Record.LatestDiscard, lastDiscarder)
	assertEqual(t, "a discard happened", lastDiscarder.OK, true)
}

func sliceArrays(v reflect.Value, into map[uintptr]bool) {
	switch kind := v.Kind(); {
	case kind == reflect.Slice:
		if v.Len() > 0 {
			into[v.Pointer()] = true
		}
		for i := range v.Len() {
			sliceArrays(v.Index(i), into)
		}
	case kind == reflect.Array:
		for i := range v.Len() {
			sliceArrays(v.Index(i), into)
		}
	case kind == reflect.Struct:
		for _, field := range v.Fields() {
			sliceArrays(field, into)
		}
	case kind == reflect.Interface && !v.IsNil():
		sliceArrays(v.Elem(), into)
	}
}

func TestSeatView_ShouldShareNoSliceWithTheGame(t *testing.T) {
	riichi, _ := dealerRiichiOnHaku(t)
	ponned, _ := script(t, riichi, act(seat(t, 2), firstPon(t, riichi, seat(t, 2))))
	ronned, _ := script(t, threePinWithTwoRonCallers(t), act(seat(t, 0), play.RonAction()), act(seat(t, 3), play.RonAction()))

	for _, c := range []struct {
		name string
		g    game.Game
	}{{"after a pon", ponned}, {"after a double ron", ronned}} {
		state := map[uintptr]bool{}
		sliceArrays(reflect.ValueOf(c.g), state)
		for _, s := range tile.Seats() {
			view := map[uintptr]bool{}
			sliceArrays(reflect.ValueOf(c.g.SeatView(s)), view)
			for data := range view {
				if state[data] {
					t.Errorf("%s, seat %d: the view shares a slice with the game", c.name, s.Index())
				}
			}
		}
	}
}
