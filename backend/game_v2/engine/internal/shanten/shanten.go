package shanten

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const Complete = -1

const (
	tilesPerSet  = 3
	fullHandSets = 4
	sevenPairs   = 7
	kokushiKinds = 13
)

// TooManyTilesError reports a hand of more than 14 tiles.
type TooManyTilesError struct {
	Count int
}

func (e TooManyTilesError) Error() string {
	return "a hand of " + strconv.Itoa(e.Count) + " tiles, more than 14"
}

// InvalidTileCountError reports a hand of a multiple of 3 tiles: called melds take 3 each from 13
// or 14.
type InvalidTileCountError struct {
	Count int
}

func (e InvalidTileCountError) Error() string {
	return "a hand of " + strconv.Itoa(e.Count) + " tiles, a multiple of 3"
}

func Lowest(c tile.Counts) (int, error) {
	counts := c.Array()
	total := 0
	for _, count := range counts {
		total += int(count)
	}

	if total > tile.MaxConcealedTiles {
		return 0, TooManyTilesError{Count: total}
	}

	if total%tilesPerSet == 0 {
		return 0, InvalidTileCountError{Count: total}
	}

	sets := total / tilesPerSet
	lowest := standardReplacementNumber(counts, sets) - 1
	if sets >= fullHandSets {
		lowest = min(lowest, Chiitoitsu(c), Kokushi(c))
	}

	return lowest, nil
}

// Chiitoitsu returns the shanten of the chiitoitsu (seven pairs) shape, for a hand of any size.
func Chiitoitsu(c tile.Counts) int {
	pairs, kinds := 0, 0
	for _, count := range c.Array() {
		if count >= 2 {
			pairs++
		}

		if count >= 1 {
			kinds++
		}
	}

	return sevenPairs - 1 - pairs + max(0, sevenPairs-kinds)
}

// Kokushi returns the shanten of the kokushi (thirteen orphans) shape, for a hand of any size.
func Kokushi(c tile.Counts) int {
	counts := c.Array()
	unique, pair := 0, 0
	for _, kind := range tile.TerminalAndHonorKinds() {
		if counts[kind] >= 1 {
			unique++
		}

		if counts[kind] >= 2 {
			pair = 1
		}
	}

	return kokushiKinds - unique - pair
}
