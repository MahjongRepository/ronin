package testkit_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func ids(t *testing.T, ns ...int) []tile.TileID {
	t.Helper()
	got := make([]tile.TileID, len(ns))
	for i, n := range ns {
		id, ok := tile.NewTileID(n)
		if !ok {
			t.Fatalf("NewTileID(%d) refused", n)
		}
		got[i] = id
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

func isError[E error](err error) bool {
	_, ok := errors.AsType[E](err)
	return ok
}

func notenGame(t *testing.T) game.Game {
	t.Helper()
	w, err := testkit.NotenWall()
	if err != nil {
		t.Fatalf("NotenWall error = %v", err)
	}
	g, err := testkit.BegunGame(w, play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("BegunGame error = %v", err)
	}
	return g
}

func TestCopies_ShouldCountEachKindsCopiesFromTheFirstGiven(t *testing.T) {
	got, err := testkit.Copies(1, "1m21m")

	if err != nil || !slices.Equal(got, ids(t, 1, 5, 2)) {
		t.Errorf("Copies = %v, %v, want 1 5 2", got, err)
	}
}

func TestCopies_WhenTheNotationIsInvalidOrPastTheFourthCopy_ShouldReportIt(t *testing.T) {
	if _, err := testkit.Copies(0, "1x"); !isError[tile.InvalidCharacterError](err) {
		t.Errorf("Copies(1x) error = %v, want InvalidCharacterError", err)
	}

	_, err := testkit.Copies(3, "11m")
	if !errors.Is(err, testkit.CopyOutOfRangeError{Notation: "11m"}) {
		t.Errorf("Copies(3, 11m) error = %v, want CopyOutOfRangeError", err)
	}
	if got, want := err.Error(), `"11m" repeats a kind past its copies`; got != want {
		t.Errorf("Error() = %q, want %q", got, want)
	}
}

func TestStartWall_ShouldDealItsHandsAndStageDrawsDeadWallAndUra(t *testing.T) {
	for _, dealer := range []tile.Seat{seat(t, 0), seat(t, 2)} {
		var hands [tile.SeatCount][]tile.TileID
		hands[0] = ids(t, 0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16)
		hands[1] = ids(t, 36, 40, 44, 48, 52, 56, 60, 64, 68, 72, 76, 80, 84)
		hands[3] = ids(t, 108, 109, 110, 112, 113, 114, 116, 117, 118, 120, 121, 122, 124)
		start := testkit.StartWall{
			Hands:   hands,
			Draws:   ids(t, 135, 3, 7),
			Rinshan: ids(t, 11, 15),
			Dora:    play.Some(ids(t, 17)[0]),
			KanDora: ids(t, 18),
			Ura:     ids(t, 19, 20),
		}
		tiles, err := start.Tiles(dealer)
		if err != nil {
			t.Fatalf("Tiles error = %v", err)
		}
		w, err := wall.FromTiles(tiles)
		if err != nil {
			t.Fatalf("FromTiles error = %v", err)
		}

		dealt := w.Deal(dealer)
		for _, n := range []int{0, 1, 3} {
			if !slices.Equal(dealt[n][:], hands[n]) {
				t.Errorf("dealer %d: hand %d = %v, want %v", dealer.Index(), n, dealt[n], hands[n])
			}
		}

		if got := w.DoraIndicators(); !slices.Equal(got, ids(t, 17)) {
			t.Errorf("dora indicators = %v, want 17", got)
		}
		var drawn []tile.TileID
		for range 3 {
			id, _ := w.Draw()
			drawn = append(drawn, id)
		}
		for range 2 {
			id, _ := w.DrawRinshan()
			drawn = append(drawn, id)
		}
		kanDora, _ := w.AddDoraIndicator()
		if want := ids(t, 135, 3, 7, 11, 15); !slices.Equal(drawn, want) || kanDora != ids(t, 18)[0] {
			t.Errorf("draws = %v and kan dora %v, want %v and 18", drawn, kanDora, want)
		}
		if got := w.UraIndicators(); !slices.Equal(got, ids(t, 19, 20)) {
			t.Errorf("ura indicators = %v, want 19 20", got)
		}
		held := slices.Concat(dealt[0][:], dealt[1][:], dealt[2][:], dealt[3][:], drawn)
		if err := wall.CheckOwnership(w, slices.Values(held)); err != nil {
			t.Errorf("CheckOwnership error = %v", err)
		}
	}
}

func TestStartWallTiles_WhenARoleOverflowsOrATileRepeats_ShouldReportTheLayout(t *testing.T) {
	for _, c := range []struct {
		w    testkit.StartWall
		want string
	}{
		{testkit.StartWall{Rinshan: ids(t, 0, 1, 2, 3, 4)}, "start wall: too many rinshan tiles: 5"},
		{testkit.StartWall{Draws: ids(t, 5), Ura: ids(t, 5)}, "start wall: tile 5 is placed twice"},
	} {
		_, err := c.w.Tiles(seat(t, 0))
		if !isError[testkit.WallLayoutError](err) || err.Error() != c.want {
			t.Errorf("Tiles error = %v, want %q", err, c.want)
		}
	}
}

func TestBegunGame_WhenTheWallCannotBeLaidOut_ShouldReportIt(t *testing.T) {
	w := testkit.StartWall{Draws: ids(t, 5, 5)}

	if _, err := testkit.BegunGame(w, play.Option[play.StartPosition]{}); !isError[testkit.WallLayoutError](err) {
		t.Errorf("BegunGame error = %v, want WallLayoutError", err)
	}
}

func TestScript_WhenAnActionIsRefused_ShouldStopThereWithTheEarlierEvents(t *testing.T) {
	g := notenGame(t)
	drawn, _ := testkit.Drawn(g)

	next, events, err := testkit.Script(g,
		testkit.SeatAction{Seat: seat(t, 0), Action: play.DiscardAction(drawn)},
		testkit.SeatAction{Seat: seat(t, 0), Action: play.TsumoAction()},
	)

	want := testkit.RefusedError{
		Seat:    seat(t, 0),
		Action:  play.TsumoAction(),
		Refusal: play.Refusal{Kind: play.RefusalNotAwaited, Code: play.CodeSeatNotAwaited},
	}
	if !errors.Is(err, want) || len(events) == 0 {
		t.Errorf("Script error = %v with %d events, want %v after the discard", err, len(events), want)
	}
	if got, msg := err.Error(), "seat 0's action of kind 3 is refused: seat_not_awaited"; got != msg {
		t.Errorf("Error() = %q, want %q", got, msg)
	}
	if held := len(next.Hand(seat(t, 0))); held != wall.StartingHandSize {
		t.Errorf("seat 0 holds %d tiles, want the game after its discard", held)
	}
}

func TestDiscardDrawnAndPlayDefaults_WhenNoTurnAfterADrawIsAwaited_ShouldReportIt(t *testing.T) {
	g, err := testkit.PlayDefaultsWhileLiveTilesExceed(notenGame(t), -1)
	if !errors.Is(err, testkit.NotInPlayError{}) || err.Error() != "no round is in play" {
		t.Errorf("PlayDefaultsWhileLiveTilesExceed error = %v, want NotInPlayError", err)
	}

	_, _, err = testkit.DiscardDrawn(g, 1)
	if !errors.Is(err, testkit.NoDrawnTileError{}) || err.Error() != "the game awaits no turn after a draw" {
		t.Errorf("DiscardDrawn error = %v, want NoDrawnTileError", err)
	}
}

func TestFirstPon_WhenTheSeatAnswersNoPrompt_ShouldReportIt(t *testing.T) {
	_, err := testkit.FirstPon(notenGame(t), seat(t, 0))

	if !errors.Is(err, testkit.NoPonError{}) || err.Error() != "the seat has no pon to call" {
		t.Errorf("FirstPon error = %v, want NoPonError", err)
	}
}

func TestEventExtractors_WhenTheEventsHoldNoRoundEnd_ShouldFindNoResult(t *testing.T) {
	g, events, err := game.New(play.Seeded{}, play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("New error = %v", err)
	}

	if kinds := testkit.EventKinds(events); kinds[0] != "started" || kinds[len(kinds)-1] != "drew" {
		t.Errorf("event kinds = %v, want started first and drew last", kinds)
	}
	if _, ok := testkit.RoundResult(events); ok {
		t.Error("RoundResult found a result")
	}
	if _, ok := testkit.FirstWin(events); ok {
		t.Error("FirstWin found a win")
	}
	if _, ok := testkit.Drawn(g); !ok {
		t.Error("Drawn found no dealer draw")
	}
}
