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

	g, _, err := New(play.RulesetTenhou, play.Seeded{Seed: seed}, play.Option[play.StartPosition]{})
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
		name      string
		standings play.Standings
		want      error
	}{
		{
			name:      "duplicate placements",
			standings: play.Standings{Scores: scores, Placements: [tile.SeatCount]int{1, 2, 2, 4}},
			want:      PlacementsError{Placements: [tile.SeatCount]int{1, 2, 2, 4}},
		},
		{
			name:      "final points off zero",
			standings: play.Standings{Scores: scores, Placements: [tile.SeatCount]int{1, 2, 3, 4}, Points: [tile.SeatCount]int{1}},
			want:      FinalPointsError{Points: 1},
		},
		{
			name:      "final scores off total",
			standings: play.Standings{Scores: [tile.SeatCount]int{25000}, Placements: [tile.SeatCount]int{1, 2, 3, 4}},
			want:      FinalScoresError{Found: 25000, Expected: 100000},
		},
		{
			name:      "valid standings",
			standings: play.Standings{Scores: scores, Placements: [tile.SeatCount]int{4, 3, 2, 1}},
		},
	} {
		t.Run(c.name, func(t *testing.T) {
			g.standings = play.Some(c.standings)

			if err := g.CheckInvariants(); !errors.Is(err, c.want) {
				t.Errorf("CheckInvariants(%+v) error = %v, want %v", c.standings, err, c.want)
			}
		})
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
		name string
		err  error
		want string
	}{
		{name: "invalid wall", err: InvalidWallError{Err: duplicate}, want: "a fixed wall is not every tile id once"},
		{name: "no fixed wall", err: NoFixedWallError{}, want: "no fixed wall is given"},
		{name: "start score off hundreds", err: StartScoreOffHundredsError{}, want: "a start score is not a whole number of hundreds"},
		{name: "start score below tobi", err: StartScoreBelowTobiError{}, want: "a start score is below the tobi threshold"},
		{name: "negative start count", err: NegativeStartCountError{}, want: "a start honba or riichi stick count is negative"},
		{name: "start points off total", err: StartPointsOffTotalError{}, want: "the start scores and riichi sticks are off the table total"},
		{name: "start in north", err: StartInNorthError{}, want: "a start is in North"},
		{name: "start in west", err: StartInWestError{}, want: "a start is in West, which the ruleset never plays"},
		{name: "ownership", err: OwnershipError{Err: wall.MissingTileError{}}, want: "tile ownership: tile 0 is nowhere"},
		{name: "table points", err: TablePointsError{Found: 100100, Expected: 100000}, want: "scores and riichi sticks total 100100, not 100000"},
		{name: "final scores", err: FinalScoresError{Found: 99000, Expected: 100000}, want: "final scores total 99000, not 100000"},
		{name: "final points", err: FinalPointsError{Points: 1}, want: "final points total 1, not 0"},
		{name: "placements", err: PlacementsError{Placements: [tile.SeatCount]int{1, 2, 2, 4}}, want: "placements [1 2 2 4] do not rank the seats 1 to 4"},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := c.err.Error(); got != c.want {
				t.Errorf("%T.Error() = %q, want %q", c.err, got, c.want)
			}
		})
	}
}
