package game

import (
	"fmt"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// InvalidWallError reports a fixed wall that does not hold every tile id exactly once; Err is the
// wall's error, which names the first tile listed twice.
type InvalidWallError struct {
	Err error
}

func (e InvalidWallError) Error() string {
	return "a fixed wall is not every tile id once"
}

func (e InvalidWallError) Unwrap() error {
	return e.Err
}

// NoFixedWallError reports a setup with no wall to deal: an empty Fixed list, or no source.
type NoFixedWallError struct{}

func (NoFixedWallError) Error() string {
	return "no fixed wall is given"
}

// StartScoreOffHundredsError reports Seat's start score that is not a whole number of hundreds.
type StartScoreOffHundredsError struct {
	Seat tile.Seat
}

func (StartScoreOffHundredsError) Error() string {
	return "a start score is not a whole number of hundreds"
}

// StartScoreBelowTobiError reports Seat's start score below the tobi threshold, which ends a game.
type StartScoreBelowTobiError struct {
	Seat tile.Seat
}

func (StartScoreBelowTobiError) Error() string {
	return "a start score is below the tobi threshold"
}

// NegativeStartCountError reports a start position with negative honba or riichi sticks.
type NegativeStartCountError struct{}

func (NegativeStartCountError) Error() string {
	return "a start honba or riichi stick count is negative"
}

// StartPointsOffTotalError reports start scores and riichi sticks that do not add up to the points
// every game holds. Found saturates at math.MaxInt.
type StartPointsOffTotalError struct {
	Found, Expected int
}

func (StartPointsOffTotalError) Error() string {
	return "the start scores and riichi sticks are off the table total"
}

// StartInNorthError reports a start in North, which a hanchan never reaches, or past it.
type StartInNorthError struct{}

func (StartInNorthError) Error() string {
	return "a start is in North"
}

// OwnershipError reports a tile missing or in more than one place; Err is the wall's error naming
// it.
type OwnershipError struct {
	Err error
}

func (e OwnershipError) Error() string {
	return "tile ownership: " + e.Err.Error()
}

func (e OwnershipError) Unwrap() error {
	return e.Err
}

// TablePointsError reports scores and riichi sticks that no longer add up to the starting points.
type TablePointsError struct {
	Found, Expected int
}

func (e TablePointsError) Error() string {
	return "scores and riichi sticks total " + strconv.Itoa(e.Found) + ", not " + strconv.Itoa(e.Expected)
}

// FinalScoresError reports final scores that do not add up to the starting points.
type FinalScoresError struct {
	Found, Expected int
}

func (e FinalScoresError) Error() string {
	return "final scores total " + strconv.Itoa(e.Found) + ", not " + strconv.Itoa(e.Expected)
}

// FinalPointsError reports final points that do not sum to 0.
type FinalPointsError struct {
	Points int
}

func (e FinalPointsError) Error() string {
	return "final points total " + strconv.Itoa(e.Points) + ", not 0"
}

// PlacementsError reports final places, by seat, that are not 1 to 4.
type PlacementsError struct {
	Placements [tile.SeatCount]int
}

func (e PlacementsError) Error() string {
	return fmt.Sprintf("placements %v are not 1 to 4", e.Placements)
}
