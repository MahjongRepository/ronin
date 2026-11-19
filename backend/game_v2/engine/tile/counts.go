package tile

import "strconv"

// Counts holds how many tiles of each kind a group of tiles holds, at most four of each. Red fives
// count as their kind.
type Counts struct {
	counts [KindCount]uint8
}

// CountsFromTiles counts the tiles of each kind; a TooManyCopiesError for the lowest kind with
// more than four tiles.
func CountsFromTiles(tiles []Tile) (Counts, error) {
	var counts [KindCount]int
	for _, t := range tiles {
		counts[t.Kind()]++
	}
	return newCounts(counts)
}

// CountsFromArray takes counts indexed by kind; a TooManyCopiesError for the lowest kind with more
// than four tiles.
func CountsFromArray(counts [KindCount]uint8) (Counts, error) {
	return newCounts(counts)
}

func newCounts[N uint8 | int](counts [KindCount]N) (Counts, error) {
	var valid Counts
	for kind, count := range counts {
		if count > CopiesPerKind {
			return Counts{}, TooManyCopiesError{Kind: Kind(kind)}
		}
		valid.counts[kind] = uint8(count)
	}
	return valid, nil
}

// Count returns how many tiles of t's kind there are, a red five counting as its kind.
func (c Counts) Count(t Tile) int {
	return int(c.counts[t.Kind()])
}

// Array returns the counts indexed by kind.
func (c Counts) Array() [KindCount]uint8 {
	return c.counts
}

// TooManyCopiesError reports more than four tiles of one kind.
type TooManyCopiesError struct {
	Kind Kind
}

func (e TooManyCopiesError) Error() string {
	return "kind " + strconv.Itoa(int(e.Kind)) + " has more than 4 tiles"
}
