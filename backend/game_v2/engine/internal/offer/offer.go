// Package offer holds the rules of a seat's options, read from the tiles and facts the seat
// knows: which tiles it may discard, which riichi, kans and meld calls it is offered, whether a
// discard or a robbed kan is a ron it may take or furiten forbids, what a win is worth and what
// it moves between the seats, and the abortive draws a hand or the first discards cause. The
// round and game machines build on it, and so does the facade's settlement of a win, so a win is
// scored and settled the same wherever it is asked.
//
// The helpers take a hand and melds the engine built, which hold every tile id once, so a kind
// at most four times; the Checked forms first check a hand and melds given from outside.
package offer

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// TurnDiscards returns the tiles a seat may discard on its turn, in hand order: in riichi after a
// draw only the drawn tile, else every held tile not of a kuikae kind.
func TurnDiscards(
	hand []tile.TileID, drawn play.Option[tile.TileID], inRiichi bool, kuikae []tile.Kind,
) []tile.TileID {
	if drawn.OK && inRiichi {
		return []tile.TileID{drawn.Value}
	}

	discards := make([]tile.TileID, 0, len(hand))
	for _, held := range hand {
		if !slices.Contains(kuikae, held.Kind()) {
			discards = append(discards, held)
		}
	}
	return discards
}

// IsHaitei reports whether a draw with liveTiles left after it is the haitei, the last live tile:
// never a rinshan draw.
func IsHaitei(liveTiles int, rinshan bool) bool {
	return liveTiles == 0 && !rinshan
}

// IsHoutei reports whether a call prompt with liveTiles left is on the houtei, the last discard:
// never a kan's tile.
func IsHoutei(liveTiles int, source play.CallSource) bool {
	return liveTiles == 0 && source == play.SourceDiscard
}

func countsOfDistinctIDs(ids []tile.TileID) tile.Counts {
	counts, _ := tile.KindCounts(ids)
	return counts
}

func meldedTiles(melds []play.MeldView) []tile.TileID {
	var tiles []tile.TileID
	for _, view := range melds {
		tiles = append(tiles, view.Tiles...)
	}
	return tiles
}

func isRed(id tile.TileID) bool {
	return id.Tile(rules.AkaDora).IsRed()
}
