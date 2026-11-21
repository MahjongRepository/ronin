// Package shanten counts how many tiles a closed hand is from tenpai: the lowest shanten over the
// regular shape of sets and a pair, chiitoitsu and kokushi, and the chiitoitsu and kokushi shanten
// alone. Complete is a complete hand, 0 tenpai. The tiles of called melds are left out of the
// counts, so a hand holds 3n+1 or 3n+2 tiles, at most 14.
//
// Lowest is xiangting's replacement number less one: the fewest tiles that, drawn in place of
// others, complete the hand, no kind ever counted past its four copies. The regular shape's number
// comes from two precomputed maps, one for a suit and one for the honors, each holding the
// numbers of one group's counts for zero or one pair and zero to four sets; the four groups'
// entries are combined by a min-plus convolution over the sets and the pair.
//
// Sources:
//
//   - The replacement number, the hash tables and the maps: xiangting 6.0.2 (MIT) by Apricot S.,
//     https://github.com/Apricot-S/xiangting. Its four-player code for the standard shape, seven
//     pairs and thirteen orphans is ported without the three-player branches; its maps are
//     extracted from the published crate's source by extract_maps.go, which also generates
//     lookup_hash.go. The blobs are little-endian uint32 arrays:
//     shupai_replacement_number.bin, 405,350 entries, SHA-256
//     ffdf76609e52f9dc416dc07267c4e7c4bc3355c8a64c237b1480ded050b4bd10;
//     zipai_replacement_number.bin, 43,130 entries, SHA-256
//     53d73840b85b5a00321d87b6f332e608ea7feb87d640310c7d1ab329b7598eb7.
//   - xiangting's algorithm: tomohxx's set recurrence,
//     https://qiita.com/tomohxx/items/75b5f771285e1334c0a5 and
//     https://tomohxx.github.io/mahjong-algorithm-book/srf/, and Cryolite's Nyanten,
//     https://qiita.com/Cryolite/items/75d504c7489426806b87.
//
// xiangting's license is in THIRD-PARTY-NOTICES.md at the module root.
//
// The tests compare every function with a fixed reference set (testdata/). An
// opt-in exhaustive check compares Lowest, for every hand of the sizes it runs, with an
// independent count of the replacement number:
//
//	go test -tags exhaustive -timeout 0 -run 'TestLowest_WhenEveryHandOfASizeIsCounted/size_07' ./engine/internal/shanten
package shanten

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Complete is the shanten of a complete hand.
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

// Lowest returns the lowest shanten of a closed hand over the regular, chiitoitsu and kokushi
// shapes; chiitoitsu and kokushi count only for a hand of 13 or 14 tiles. A TooManyTilesError or
// an InvalidTileCountError for a tile count no hand has.
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
