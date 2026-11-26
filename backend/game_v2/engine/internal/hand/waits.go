package hand

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

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
