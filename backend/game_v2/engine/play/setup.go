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

// StartPosition is a game state to start from instead of East 1 with the starting scores. Scores
// are by seat; Honba and RiichiSticks count 0 or more; RoundNumber counts every hand played
// before this one, which also picks a seeded wall. A game accepts only a position it can reach:
// every score a whole number of hundreds at or above the tobi threshold, the scores and the
// riichi sticks adding up to four starting scores, and the wind East, South or West.
type StartPosition struct {
	Scores       [tile.SeatCount]int
	Honba        int
	RiichiSticks int
	Dealer       tile.Seat
	Wind         tile.Wind
	RoundNumber  uint32
}

// RoundDeal is one round as its seed breaks and deals it, for the tools that sample the seed: the
// live wall before the deal in draw order; the dead wall's 14 tiles, the 4 rinshan tiles in draw
// order and then each of the 5 indicator stacks top then bottom (not the 7 tops then 7 bottoms of a
// fixed wall); the first dora indicator; each seat's starting hand sorted by id; and the dealer's
// first draw.
type RoundDeal struct {
	Live          []tile.TileID
	DeadWall      []tile.TileID
	DoraIndicator tile.TileID
	Hands         [tile.SeatCount][]tile.TileID
	DealerDraw    tile.TileID
}
