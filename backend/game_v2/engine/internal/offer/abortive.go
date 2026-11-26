package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const kyuushuMinKinds = 9

// HasNineTerminalKinds reports whether a drawn hand shows enough distinct terminal and honor kinds
// for kyuushu kyuuhai.
func HasNineTerminalKinds(hand []tile.TileID) bool {
	var kinds tile.Kinds
	for _, id := range hand {
		if id.Kind().IsTerminalOrHonor() {
			kinds = kinds.With(id.Kind())
		}
	}

	return kinds.Len() >= kyuushuMinKinds
}

// IsFourWinds reports whether the discards of the round, in order, are exactly the first four and
// all the same wind.
func IsFourWinds(discards []tile.TileID) bool {
	if len(discards) != tile.SeatCount {
		return false
	}

	winds := tile.WindKinds()
	first := discards[0].Kind()
	sameKind := !slices.ContainsFunc(discards, func(id tile.TileID) bool { return id.Kind() != first })
	return slices.Contains(winds[:], first) && sameKind
}
