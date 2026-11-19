package record_test

import (
	"reflect"
	"slices"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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

func tileOf(t *testing.T, mpsz string) tile.TileID {
	t.Helper()
	got := copies(t, 0, mpsz)
	if len(got) != 1 {
		t.Fatalf("%q holds %d tiles, want 1", mpsz, len(got))
	}
	return got[0]
}

func junk(t *testing.T, first int) []tile.TileID {
	t.Helper()
	got, err := testkit.Junk(first)
	if err != nil {
		t.Fatalf("Junk(%d) error = %v", first, err)
	}
	return got
}

func begun(t *testing.T, w testkit.StartWall) game.Game {
	t.Helper()
	g, err := testkit.BegunGame(w, play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("BegunGame error = %v", err)
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

func firstPon(t *testing.T, g game.Game, s tile.Seat) play.Action {
	t.Helper()
	pon, err := testkit.FirstPon(g, s)
	if err != nil {
		t.Fatalf("FirstPon error = %v", err)
	}
	return pon
}

func threePinWithTwoRonCallers(t *testing.T) game.Game {
	t.Helper()
	g, err := testkit.ThreePinWithTwoRonCallers()
	if err != nil {
		t.Fatalf("ThreePinWithTwoRonCallers error = %v", err)
	}
	return g
}

func doubleRiichiWall(t *testing.T, firstDrawAfter tile.TileID) testkit.StartWall {
	t.Helper()
	return testkit.StartWall{
		Hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m123p9s"),
			junk(t, 1),
			slices.Concat(copies(t, 2, "1357m2468p135s"), copies(t, 1, "55z")),
			junk(t, 3),
		},
		Draws: []tile.TileID{
			tileOf(t, "1z"), firstDrawAfter, tileOf(t, "3z"), tileOf(t, "4z"), tileOf(t, "6z"),
		},
	}
}

func everyField() cmp.Options {
	return cmp.Options{cmp.Exporter(func(reflect.Type) bool { return true }), cmpopts.EquateEmpty()}
}

func assertEqual[T any](t *testing.T, what string, got, want T) {
	t.Helper()
	if diff := cmp.Diff(want, got, everyField()); diff != "" {
		t.Errorf("%s differs (-want +got):\n%s", what, diff)
	}
}

func followed(t *testing.T, g game.Game, r play.SeatRecord, actions ...testkit.SeatAction) (game.Game, play.SeatRecord) {
	t.Helper()
	g, events := script(t, g, actions...)
	for _, e := range events {
		r = record.Apply(r, e)
	}
	assertEqual(t, "record", r, g.SeatView(r.Seat).Record)
	return g, r
}
