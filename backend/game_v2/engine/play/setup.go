package play

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// WallSource is where a game's walls come from: Seeded or Fixed.
//
//sumtype:decl
type WallSource interface {
	isWallSource()
}

// Seeded takes every round's wall, the first dealer and the dice from Seed, a shake256-v1 seed of
// 96 bytes.
type Seeded struct {
	Seed [96]byte
}

// Fixed takes one explicit wall per round in turn: 122 live tiles in draw order, then the 7 dead
// wall tops, then the 7 bottoms. Seat 0 deals first and every throw is (1, 1).
type Fixed struct {
	Walls [][tile.TileIDCount]tile.TileID
}

func (Seeded) isWallSource() {}
func (Fixed) isWallSource()  {}
