package hand

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// ClosedWaits returns the kinds that complete a closed part of 3n+1 tiles, judged on the closed
// part alone: copies in melds are not seen, and a kind already held four times in the closed part
// is never a wait. It covers sets and a pair, seven pairs and thirteen orphans, and is empty when
// the closed part is not tenpai, or empty or not 3n+1 tiles.
func ClosedWaits(closed tile.Counts) tile.Kinds {
	counts := closed.Array()
	if total(counts)%setTiles != 1 || isOneShantenOrWorse(closed) {
		return tile.Kinds{}
	}

	var waits tile.Kinds
	for kind, count := range counts {
		if count >= tile.CopiesPerKind {
			continue
		}
		completed := counts
		completed[kind]++
		if isAgari(completed) {
			waits = waits.With(tile.Kind(kind))
		}
	}
	return waits
}

// Waits returns the formal waits of a closed part of 3n+1 tiles with the player's own melded
// tiles, a kan counting all four: ClosedWaits less every kind the closed part and the melded tiles
// hold four copies of (karaten). Copies outside the player's hand, in other rivers, melds or the
// wall, never matter. Empty when the hand is not tenpai, or the closed part is empty or not 3n+1
// tiles.
func Waits(closed, melded tile.Counts) tile.Kinds {
	closedCounts, meldedCounts := closed.Array(), melded.Array()
	var heldOut tile.Kinds
	for kind := range closedCounts {
		if closedCounts[kind]+meldedCounts[kind] >= tile.CopiesPerKind {
			heldOut = heldOut.With(tile.Kind(kind))
		}
	}
	return ClosedWaits(closed).Difference(heldOut)
}

// IsTenpai reports whether a closed part of 3n+1 tiles with the player's own melded tiles is
// formally tenpai: its Waits are not empty.
func IsTenpai(closed, melded tile.Counts) bool {
	return !Waits(closed, melded).IsEmpty()
}

// TenpaiDiscards returns the kinds whose discard from a drawn closed part of 3n+2 tiles leaves the
// hand formally tenpai, karaten judged on the tiles left after each discard. A complete hand keeps
// every discard that leaves waits. Empty when no discard keeps tenpai, or the closed part is not
// 3n+2 tiles.
func TenpaiDiscards(closed, melded tile.Counts) tile.Kinds {
	if total(closed.Array())%setTiles != 2 || isOneShantenOrWorse(closed) {
		return tile.Kinds{}
	}

	var discards tile.Kinds
	for kind := range tile.Kind(tile.KindCount) {
		rest, ok := closed.WithoutOne(kind)
		if ok && IsTenpai(rest, melded) {
			discards = discards.With(kind)
		}
	}
	return discards
}

func isOneShantenOrWorse(closed tile.Counts) bool {
	lowest, err := shanten.Lowest(closed)
	return err == nil && lowest >= 1
}
