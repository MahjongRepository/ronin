package game_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func seatOneTenpaiOnThreePinHand(t *testing.T) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 0, "123456789m12p5p"), copies(t, 1, "5p"))
}

func seatOneTenpaiOnThreePin(t *testing.T) game.Game {
	t.Helper()
	w := testkit.StartWall{Hands: [tile.SeatCount][]tile.TileID{
		junk(t, 1), seatOneTenpaiOnThreePinHand(t), junk(t, 2), junk(t, 3),
	}}
	return begun(t, w, noStart())
}

func TestExhaustiveDraw_WhenTheLastDiscardHasNoCallers_ShouldEndTheRound(t *testing.T) {
	g := playDefaultsWhileLiveTilesExceed(t, seatOneTenpaiOnThreePin(t), 0)
	assertEqual(t, "awaiting", g.Awaiting(), awaitingTurn(seat(t, 1)))
	decision, _ := g.Decision(seat(t, 1))
	if draw, ok := decision.Context.(play.TurnAfterDraw); !ok || !draw.Haitei {
		t.Errorf("context = %+v, want the haitei draw", decision.Context)
	}
	header := g.Header()

	g, events := script(t, g, act(seat(t, 1), decision.Default))

	tenpaiHand := seatOneTenpaiOnThreePinHand(t)
	slices.SortFunc(tenpaiHand, tile.TileID.Compare)
	result := play.ExhaustiveDraw{
		Tenpai:       []play.ShownHand{{Seat: seat(t, 1), Hand: tenpaiHand}},
		ScoreChanges: [tile.SeatCount]int{-1000, 3000, -1000, -1000},
	}
	scores := [tile.SeatCount]int{24000, 28000, 24000, 24000}
	assertEqual(t, "kinds", testkit.EventKinds(events), []string{"discarded", "round_ended"})
	assertEqual(t, "round end", events[1], play.Emitted{To: play.ToAll(), Event: play.RoundEnded{
		Result: result, Scores: scores,
	}})
	assertEqual(t, "phase", g.Phase(), play.PhaseRoundOver)
	assertEqual(t, "awaiting", g.Awaiting(), play.Awaiting(play.AwaitingRoundOver{}))
	assertEqual(t, "history", g.History(), []play.FinishedRound{{Header: header, Result: result}})
	assertEqual(t, "scores", g.Scores(), scores)
	assertEqual(t, "header", g.Header(), header)
	if err := g.CheckOwnership(); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}
}

func TestAct_WhenTheRoundIsOver_ShouldRefuseEveryPlayCallAndChangeNothing(t *testing.T) {
	g := playDefaultsWhileLiveTilesExceed(t, seatOneTenpaiOnThreePin(t), 0)
	last, _ := g.DefaultAction(seat(t, 1))
	g, _ = script(t, g, act(seat(t, 1), last))

	assertRefused(t, g, seat(t, 2), play.DiscardAction(g.Hand(seat(t, 2))[0]),
		refusal(play.RefusalNotAwaited, play.CodeWrongPhase))
	for _, s := range tile.Seats() {
		if _, ok := g.Decision(s); ok || len(g.LegalActions(s)) != 0 {
			t.Errorf("seat %d is offered actions in a round over", s.Index())
		}
	}
}
