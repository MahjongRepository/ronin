package game

import (
	"errors"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func seededGame(t *testing.T) Game {
	t.Helper()
	seed, err := rng.ParseSeed(strings.Repeat("ab", rng.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	g, _, err := New(play.Seeded{Seed: seed}, play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("New error = %v", err)
	}
	return g
}

func TestCheckInvariants_WhenPointsAppearFromNowhere_ShouldFindThem(t *testing.T) {
	g := seededGame(t)
	g.points.ApplyChanges([tile.SeatCount]int{100, 0, 0, 0})

	if err := g.CheckInvariants(); !errors.Is(err, TablePointsError{Found: 100100, Expected: 100000}) {
		t.Errorf("CheckInvariants error = %v, want TablePointsError found 100100", err)
	}
}

func TestCheckInvariants_WhenTheFinalStandingsBreakTheTotals_ShouldFindThem(t *testing.T) {
	g := seededGame(t)
	scores := [tile.SeatCount]int{25000, 25000, 25000, 25000}
	for _, c := range []struct {
		standings play.Standings
		want      error
	}{
		{play.Standings{Scores: scores, Placements: [tile.SeatCount]int{1, 2, 2, 4}}, PlacementsError{
			Placements: [tile.SeatCount]int{1, 2, 2, 4},
		}},
		{play.Standings{Scores: scores, Placements: [tile.SeatCount]int{1, 2, 3, 4}, Points: [tile.SeatCount]int{1}}, FinalPointsError{
			Points: 1,
		}},
		{play.Standings{Scores: [tile.SeatCount]int{25000}, Placements: [tile.SeatCount]int{1, 2, 3, 4}}, FinalScoresError{
			Found: 25000, Expected: 100000,
		}},
		{play.Standings{Scores: scores, Placements: [tile.SeatCount]int{4, 3, 2, 1}}, nil},
	} {
		g.standings = play.Some(c.standings)
		if err := g.CheckInvariants(); !errors.Is(err, c.want) {
			t.Errorf("CheckInvariants(%+v) error = %v, want %v", c.standings, err, c.want)
		}
	}
}

func isOwnershipError(err error) bool {
	_, ok := errors.AsType[OwnershipError](err)
	return ok
}

func TestCheckInvariants_WhenTheGameIsTheZeroValue_ShouldFindTheTilesOutOfPlace(t *testing.T) {
	var g Game

	err := g.CheckInvariants()

	if !errors.Is(err, wall.TileInTwoPlacesError{}) || !isOwnershipError(err) {
		t.Errorf("CheckInvariants error = %v, want an OwnershipError of tile 0 in two places", err)
	}
}

func TestSetupAndInvariantErrors_ShouldDescribeTheirFault(t *testing.T) {
	duplicate := wall.DuplicateTileError{}
	for _, c := range []struct {
		err  error
		want string
	}{
		{InvalidWallError{Err: duplicate}, "a fixed wall is not every tile id once"},
		{NoFixedWallError{}, "no fixed wall is given"},
		{StartScoreOffHundredsError{}, "a start score is not a whole number of hundreds"},
		{StartScoreBelowTobiError{}, "a start score is below the tobi threshold"},
		{NegativeStartCountError{}, "a start honba or riichi stick count is negative"},
		{StartPointsOffTotalError{}, "the start scores and riichi sticks are off the table total"},
		{StartInNorthError{}, "a start is in North"},
		{OwnershipError{Err: wall.MissingTileError{}}, "tile ownership: tile 0 is nowhere"},
		{TablePointsError{Found: 100100, Expected: 100000}, "scores and riichi sticks total 100100, not 100000"},
		{FinalScoresError{Found: 99000, Expected: 100000}, "final scores total 99000, not 100000"},
		{FinalPointsError{Points: 1}, "final points total 1, not 0"},
		{PlacementsError{Placements: [tile.SeatCount]int{1, 2, 2, 4}}, "placements [1 2 2 4] are not 1 to 4"},
	} {
		if got := c.err.Error(); got != c.want {
			t.Errorf("%T.Error() = %q, want %q", c.err, got, c.want)
		}
	}
}
