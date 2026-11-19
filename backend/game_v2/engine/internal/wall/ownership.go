package wall

import (
	"iter"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// MissingTileError reports a tile that neither the wall nor any held tile is.
type MissingTileError struct {
	Tile tile.TileID
}

func (e MissingTileError) Error() string {
	return "tile " + strconv.Itoa(e.Tile.Index()) + " is nowhere"
}

// TileInTwoPlacesError reports a tile that is in more than one place.
type TileInTwoPlacesError struct {
	Tile tile.TileID
}

func (e TileInTwoPlacesError) Error() string {
	return "tile " + strconv.Itoa(e.Tile.Index()) + " is in more than one place"
}

// CheckOwnership checks that each of the 136 tiles sits exactly once in w or among held, the
// tiles of the hands, rivers and melds. A MissingTileError or TileInTwoPlacesError names the
// lowest tile id that is missing or duplicated.
func CheckOwnership(w Wall, held iter.Seq[tile.TileID]) error {
	var counts [tile.TileIDCount]int
	for _, id := range w.Tiles() {
		counts[id.Index()]++
	}
	for id := range held {
		counts[id.Index()]++
	}

	for _, id := range tile.AllTileIDs() {
		switch count := counts[id.Index()]; {
		case count == 0:
			return MissingTileError{Tile: id}
		case count > 1:
			return TileInTwoPlacesError{Tile: id}
		}
	}
	return nil
}
