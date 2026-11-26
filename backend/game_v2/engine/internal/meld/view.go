package meld

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// FromView returns the meld a declared meld scores as, its ids read with the engine's aka dora;
// false when its tiles do not fit its kind. An added kan is an open kan.
func FromView(view play.MeldView) (Meld, bool) {
	var tiles [4]tile.Tile
	if len(view.Tiles) > len(tiles) {
		return Meld{}, false
	}

	for i, id := range view.Tiles {
		tiles[i] = id.Tile(rules.AkaDora)
	}

	size := 4
	if view.Kind == play.MeldChi || view.Kind == play.MeldPon {
		size = 3
	}

	if len(view.Tiles) != size {
		return Meld{}, false
	}

	var m Meld
	var err error
	switch view.Kind {
	case play.MeldChi:
		m, err = NewChi([3]tile.Tile(tiles[:3]))
	case play.MeldPon:
		m, err = NewPon([3]tile.Tile(tiles[:3]))
	case play.MeldOpenKan, play.MeldAddedKan:
		m, err = NewOpenKan(tiles)
	case play.MeldClosedKan:
		m, err = NewClosedKan(tiles)
	default:
		return Meld{}, false
	}

	return m, err == nil
}

// MisfitMeldError reports that the meld at Index does not fit its kind: FromView refuses it.
type MisfitMeldError struct {
	Index int
}

func (e MisfitMeldError) Error() string {
	return "meld " + strconv.Itoa(e.Index) + " does not fit its kind"
}

// DuplicateTileError reports a tile id held twice among a hand and its melds' tiles.
type DuplicateTileError struct {
	Tile tile.TileID
}

func (e DuplicateTileError) Error() string {
	return "tile " + strconv.Itoa(e.Tile.Index()) + " is held twice"
}

func CheckHandInput(hand []tile.TileID, melds []play.MeldView) error {
	for index, view := range melds {
		if _, ok := FromView(view); !ok {
			return MisfitMeldError{Index: index}
		}
	}

	var held [tile.TileIDCount]bool
	check := func(id tile.TileID) error {
		if held[id.Index()] {
			return DuplicateTileError{Tile: id}
		}

		held[id.Index()] = true
		return nil
	}

	for _, id := range hand {
		if err := check(id); err != nil {
			return err
		}
	}

	for _, view := range melds {
		for _, id := range view.Tiles {
			if err := check(id); err != nil {
				return err
			}
		}
	}

	return nil
}
