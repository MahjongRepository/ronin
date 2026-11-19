package game_test

import (
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

func nagashiWall(t *testing.T, hands [tile.SeatCount][]tile.TileID, qualifying tile.Seat, seatOfDraw func(int) tile.Seat) testkit.StartWall {
	t.Helper()
	w := testkit.StartWall{Hands: hands}
	var terminals, simples []tile.TileID
	for _, free := range w.UnplacedTiles() {
		if free.Kind().IsTerminalOrHonor() {
			terminals = append(terminals, free)
		} else {
			simples = append(simples, free)
		}
	}

	pop := func(tiles *[]tile.TileID) tile.TileID {
		last := (*tiles)[len(*tiles)-1]
		*tiles = (*tiles)[:len(*tiles)-1]
		return last
	}
	var drawnOnce [tile.SeatCount]bool
	for index := range wall.LiveTilesAtDeal {
		drawer := seatOfDraw(index)
		first := !drawnOnce[drawer.Index()]
		drawnOnce[drawer.Index()] = true
		switch {
		case drawer == qualifying:
			w.Draws = append(w.Draws, pop(&terminals))
		case first || len(simples) > 0:
			w.Draws = append(w.Draws, pop(&simples))
		default:
			w.Draws = append(w.Draws, pop(&terminals))
		}
	}
	return w
}

func playOut(t *testing.T, g game.Game) (game.Game, []play.Emitted) {
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
	return g, events
}

func TestExhaustiveDraw_WhenOnlyTerminalAndHonorDiscards_ShouldPayNagashiManganOverNotenPayments(t *testing.T) {
	tenpaiOnSevenSou := copies(t, 0, "234567m234p5568s")
	hands := [tile.SeatCount][]tile.TileID{tenpaiOnSevenSou, noten(t, 1), noten(t, 2), noten(t, 3)}
	w := nagashiWall(t, hands, seat(t, 0), func(index int) tile.Seat { return tile.Seats()[(index+1)%tile.SeatCount] })
	start := testkit.EastStart([tile.SeatCount]int{25000, 25000, 25000, 25000}, 0, 0)
	start.Dealer, start.RoundNumber = seat(t, 1), 1

	_, events := playOut(t, begun(t, w, play.Some(start)))

	draw, ok := roundResult(t, events).(play.ExhaustiveDraw)
	if !ok {
		t.Fatalf("result = %+v, want an exhaustive draw", roundResult(t, events))
	}
	if len(draw.Tenpai) != 1 || draw.Tenpai[0].Seat != seat(t, 0) {
		t.Fatalf("tenpai = %+v, want seat 0 alone", draw.Tenpai)
	}
	assertEqual(t, "tenpai hand", draw.Tenpai[0].Hand, tenpaiOnSevenSou)
	if len(draw.Nagashi) != 1 || draw.Nagashi[0].Seat != seat(t, 0) {
		t.Errorf("nagashi = %+v, want seat 0 alone", draw.Nagashi)
	}
	assertEqual(t, "score changes", draw.ScoreChanges, [tile.SeatCount]int{8000, -4000, -2000, -2000})
	for _, emitted := range events {
		if ended, isEnd := emitted.Event.(play.RoundEnded); isEnd && ended.Scores[0] != 33000 {
			t.Errorf("seat 0 score = %d, want 33000", ended.Scores[0])
		}
	}
}
