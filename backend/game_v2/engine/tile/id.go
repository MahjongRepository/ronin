package tile

import (
	"cmp"
	"iter"
)

// TileIDCount is the number of tiles in a set.
const TileIDCount = KindCount * CopiesPerKind

const (
	redFiveManID = 16
	redFivePinID = 52
	redFiveSouID = 88
)

// TileID is one physical tile, a 136-format id from 0 to 135: kind id / 4, so ids 0 to 35 are the
// man tiles, 36 to 71 pin, 72 to 107 sou and 108 to 135 the honors. With aka dora, ids 16, 52 and
// 88 are the red fives. Its zero value is id 0.
type TileID struct {
	n uint8
}

// NewTileID returns tile id n; false when n is not 0 to 135.
func NewTileID(n int) (TileID, bool) {
	if n < 0 || n >= TileIDCount {
		return TileID{}, false
	}
	return TileID{n: uint8(n)}, true
}

// AllTileIDs returns every tile id in ascending order.
func AllTileIDs() [TileIDCount]TileID {
	var ids [TileIDCount]TileID
	for i := range ids {
		ids[i] = TileID{n: uint8(i)}
	}
	return ids
}

// Index returns the 136-format id, an index into per-tile arrays.
func (id TileID) Index() int {
	return int(id.n)
}

// Compare returns -1, 0 or +1 as id's number is below, equal to or above other's.
func (id TileID) Compare(other TileID) int {
	return cmp.Compare(id.n, other.n)
}

// Kind returns id's kind, id / 4.
func (id TileID) Kind() Kind {
	return Kind(id.n / CopiesPerKind)
}

// Tile returns id's hand tile: a red five when aka is AkaDoraEnabled and id is 16, 52 or 88.
func (id TileID) Tile(aka AkaDora) Tile {
	if aka == AkaDoraEnabled && (id.n == redFiveManID || id.n == redFivePinID || id.n == redFiveSouID) {
		return redFiveOfSuit(int(id.Kind() / 9))
	}
	return Tile{code: uint8(id.Kind())}
}

// KindCounts counts the ids of each kind; a TooManyCopiesError for the lowest kind held more than
// four times.
func KindCounts(ids []TileID) (Counts, error) {
	var counts [KindCount]int
	for _, id := range ids {
		counts[id.Kind()]++
	}
	return newCounts(counts)
}

// HeldCopies yields the ids of kind in hand, in hand order.
func HeldCopies(hand []TileID, kind Kind) iter.Seq[TileID] {
	return func(yield func(TileID) bool) {
		for _, held := range hand {
			if held.Kind() == kind && !yield(held) {
				return
			}
		}
	}
}
