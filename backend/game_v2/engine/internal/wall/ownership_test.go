package wall_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestCheckOwnership_WhenTheWallIsDealt_ShouldHold(t *testing.T) {
	w := wall.FromSeed(fixedSeed(t), 0, seat(t, 0))
	hands := w.Deal(seat(t, 0))

	if err := wall.CheckOwnership(w, slices.Values(dealtTiles(hands))); err != nil {
		t.Errorf("CheckOwnership error = %v", err)
	}
}

func TestCheckOwnership_WhenAHeldTileIsGone_ShouldNameIt(t *testing.T) {
	w := orderedWall(t)
	held := slices.DeleteFunc(dealtTiles(w.Deal(seat(t, 0))), func(held tile.TileID) bool { return held.Index() == 7 })

	if err := wall.CheckOwnership(w, slices.Values(held)); !errors.Is(err, wall.MissingTileError{Tile: id(t, 7)}) {
		t.Errorf("CheckOwnership error = %v, want tile 7 missing", err)
	}
}

func TestCheckOwnership_WhenATileIsHeldTwice_ShouldNameIt(t *testing.T) {
	w := orderedWall(t)
	held := append(dealtTiles(w.Deal(seat(t, 0))), id(t, 100))

	if err := wall.CheckOwnership(w, slices.Values(held)); !errors.Is(err, wall.DuplicatedTileError{Tile: id(t, 100)}) {
		t.Errorf("CheckOwnership error = %v, want tile 100 duplicated", err)
	}
}
