package game_test

import (
	"reflect"
	"slices"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func id(t *testing.T, n int) tile.TileID {
	t.Helper()
	got, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
	}

	return got
}

func ids(t *testing.T, ns ...int) []tile.TileID {
	t.Helper()
	got := make([]tile.TileID, len(ns))
	for i, n := range ns {
		got[i] = id(t, n)
	}

	return got
}

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}

	return got
}

func copies(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	got, err := testkit.Copies(first, mpsz)
	if err != nil {
		t.Fatalf("Copies(%d, %q) error = %v", first, mpsz, err)
	}

	return got
}

func tileOf(t *testing.T, first int, mpsz string) tile.TileID {
	t.Helper()
	got := copies(t, first, mpsz)
	if len(got) != 1 {
		t.Fatalf("%q holds %d tiles, want 1", mpsz, len(got))
	}

	return got[0]
}

func kindOf(t *testing.T, mpsz string) tile.Kind {
	t.Helper()
	return tileOf(t, 0, mpsz).Kind()
}

func junk(t *testing.T, first int) []tile.TileID {
	t.Helper()
	got, err := testkit.Junk(first)
	if err != nil {
		t.Fatalf("Junk(%d) error = %v", first, err)
	}

	return got
}

func notenWall(t *testing.T) testkit.StartWall {
	t.Helper()
	w, err := testkit.NotenWall()
	if err != nil {
		t.Fatalf("NotenWall error = %v", err)
	}

	return w
}

func noStart() play.Option[play.StartPosition] {
	return play.Option[play.StartPosition]{}
}

func wallTiles(t *testing.T, w testkit.StartWall, dealer tile.Seat) [tile.TileIDCount]tile.TileID {
	t.Helper()
	tiles, err := w.Tiles(dealer)
	if err != nil {
		t.Fatalf("Tiles error = %v", err)
	}

	return tiles
}

func fixed(walls ...[tile.TileIDCount]tile.TileID) play.WallSource {
	return play.Fixed{Walls: walls}
}

func newGame(t *testing.T, source play.WallSource, start play.Option[play.StartPosition]) (game.Game, []play.Emitted) {
	t.Helper()
	g, dealt, err := game.New(play.RulesetTenhou, source, start)
	if err != nil {
		t.Fatalf("New error = %v", err)
	}

	g, drew, _ := g.Begin()
	return g, append(dealt, drew...)
}

func dealNextRound(t *testing.T, g game.Game) game.Game {
	t.Helper()
	g, _, refused := g.DealNextRound()
	if refused.OK {
		t.Fatalf("DealNextRound refusal = %+v", refused.Value)
	}

	g, _, refused = g.Begin()
	if refused.OK {
		t.Fatalf("Begin refusal = %+v", refused.Value)
	}

	return g
}

func begun(t *testing.T, w testkit.StartWall, start play.Option[play.StartPosition]) game.Game {
	t.Helper()
	return begunUnder(t, play.RulesetTenhou, w, start)
}

func begunUnder(t *testing.T, ruleset play.Ruleset, w testkit.StartWall, start play.Option[play.StartPosition]) game.Game {
	t.Helper()
	g, err := testkit.BegunGameUnder(ruleset, w, start)
	if err != nil {
		t.Fatalf("BegunGameUnder(%d) error = %v", ruleset, err)
	}

	return g
}

func act(s tile.Seat, action play.Action) testkit.SeatAction {
	return testkit.SeatAction{Seat: s, Action: action}
}

func script(t *testing.T, g game.Game, actions ...testkit.SeatAction) (game.Game, []play.Emitted) {
	t.Helper()
	next, events, err := testkit.Script(g, actions...)
	if err != nil {
		t.Fatalf("Script error = %v", err)
	}

	return next, events
}

func discardDrawn(t *testing.T, g game.Game, turns int) (game.Game, []play.Emitted) {
	t.Helper()
	next, events, err := testkit.DiscardDrawn(g, turns)
	if err != nil {
		t.Fatalf("DiscardDrawn error = %v", err)
	}

	return next, events
}

func playDefaultsWhileLiveTilesExceed(t *testing.T, g game.Game, liveTiles int) game.Game {
	t.Helper()
	next, err := testkit.PlayDefaultsWhileLiveTilesExceed(g, liveTiles)
	if err != nil {
		t.Fatalf("PlayDefaultsWhileLiveTilesExceed error = %v", err)
	}

	return next
}

func firstPon(t *testing.T, g game.Game, s tile.Seat) play.Action {
	t.Helper()
	pon, err := testkit.FirstPon(g, s)
	if err != nil {
		t.Fatalf("FirstPon error = %v", err)
	}

	return pon
}

func roundResult(t *testing.T, events []play.Emitted) play.RoundResult {
	t.Helper()
	result, ok := testkit.RoundResult(events)
	if !ok {
		t.Fatal("the events end no round")
	}

	return result
}

func firstWin(t *testing.T, events []play.Emitted) play.WinResult {
	t.Helper()
	win, ok := testkit.FirstWin(events)
	if !ok {
		t.Fatal("the round did not end in a win")
	}

	return win
}

func turnContext(t *testing.T, g game.Game) play.DecisionContext {
	t.Helper()
	s, ok := testkit.TurnSeat(g)
	if !ok {
		t.Fatal("no turn is awaited")
	}

	decision, _ := g.Decision(s)
	return decision.Context
}

func everyField() cmp.Options {
	return cmp.Options{cmp.Exporter(func(reflect.Type) bool { return true }), cmpopts.EquateEmpty()}
}

func assertSameGame(t *testing.T, got, want game.Game) {
	t.Helper()
	if diff := cmp.Diff(want, got, everyField()); diff != "" {
		t.Errorf("game differs (-want +got):\n%s", diff)
	}
}

func assertEqual[T any](t *testing.T, what string, got, want T) {
	t.Helper()
	if diff := cmp.Diff(want, got, everyField()); diff != "" {
		t.Errorf("%s differs (-want +got):\n%s", what, diff)
	}
}

func assertRefused(t *testing.T, build func() game.Game, s tile.Seat, action play.Action, want play.Refusal) {
	t.Helper()
	g := build()
	next, events, refusal := g.Act(s, action)
	if !refusal.OK || refusal.Value != want {
		t.Errorf("Act(%d, %v) refusal = %+v, want %+v", s.Index(), action, refusal, want)
	}

	if len(events) != 0 {
		t.Errorf("refused Act events = %v, want none", events)
	}
	assertSameGame(t, next, build())
	assertSameGame(t, g, build())
}

func awaitingTurn(s tile.Seat) play.Awaiting {
	return play.AwaitingTurn{Seat: s}
}

func awaitingCall(seats ...tile.Seat) play.Awaiting {
	return play.AwaitingCall{Seats: seats}
}

func discards(held []tile.TileID) []play.Action {
	actions := make([]play.Action, len(held))
	for i, h := range held {
		actions[i] = play.DiscardAction(h)
	}

	return actions
}

func containsAction(actions []play.Action, action play.Action) bool {
	return slices.Contains(actions, action)
}

func refusal(kind play.RefusalKind, code play.RefusalCode) play.Refusal {
	return play.Refusal{Kind: kind, Code: code}
}

func turnSeat(t *testing.T, g game.Game) tile.Seat {
	t.Helper()
	s, ok := testkit.TurnSeat(g)
	if !ok {
		t.Fatal("no turn is awaited")
	}

	return s
}

func doraFreeUra(t *testing.T) tile.TileID {
	t.Helper()
	return tileOf(t, 3, "7z")
}

func dragonFillers(t *testing.T) []tile.TileID {
	t.Helper()
	return slices.Concat(copies(t, 0, "5z"), copies(t, 1, "7z"), copies(t, 0, "7z"), copies(t, 3, "4z"))
}

func goAroundGame(
	t *testing.T, hands [tile.SeatCount][]tile.TileID, drawsAfter []tile.TileID, start play.Option[play.StartPosition],
	dora tile.TileID,
) game.Game {
	t.Helper()
	w := testkit.StartWall{
		Hands: hands,
		Draws: slices.Concat(dragonFillers(t), drawsAfter),
		Dora:  play.Some(dora),
		Ura:   []tile.TileID{doraFreeUra(t)},
	}
	g, _ := discardDrawn(t, begun(t, w, start), tile.SeatCount)
	return g
}

func sticksPaidScores(riichiSticks int) [tile.SeatCount]int {
	tenhou := rules.Tenhou()
	start := tenhou.StartingScore
	scores := [tile.SeatCount]int{start, start, start, start}
	for i := range riichiSticks {
		scores[i%tile.SeatCount] -= tenhou.RiichiStickValue
	}

	return scores
}

func yakumanCount(value play.Value) int {
	yakuman, _ := value.(play.Yakuman)
	return yakuman.Count
}

func roundEnded(t *testing.T, events []play.Emitted) play.RoundEnded {
	t.Helper()
	for _, emitted := range events {
		if ended, ok := emitted.Event.(play.RoundEnded); ok {
			return ended
		}
	}

	t.Fatal("the events end no round")
	return play.RoundEnded{}
}
