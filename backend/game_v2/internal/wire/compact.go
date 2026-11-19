package wire

import (
	"errors"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// ScoreDivisor is the points in one wire score unit: scores, payments and stick values go out
// divided by it.
const ScoreDivisor = 100

const (
	seatTileSpace = tile.SeatCount * tile.TileIDCount
	discardFlags  = 4
	tsumogiriFlag = 1
	riichiFlag    = 2
)

// Move is a draw or discard packed into one integer (KeyPackedMove): Seat moved Tile; for a
// discard, Tsumogiri when it was the tile just drawn and Riichi when it declares riichi.
type Move struct {
	Seat      tile.Seat
	Tile      tile.TileID
	Tsumogiri bool
	Riichi    bool
}

// PackDraw returns the packed draw of seat drawing t, 0 to 543.
func PackDraw(seat tile.Seat, t tile.TileID) int {
	return seat.Index()*tile.TileIDCount + t.Index()
}

// PackDiscard returns m packed as a discard, 0 to 2175.
func PackDiscard(m Move) int {
	flags := 0
	if m.Tsumogiri {
		flags |= tsumogiriFlag
	}
	if m.Riichi {
		flags |= riichiFlag
	}
	return flags*seatTileSpace + PackDraw(m.Seat, m.Tile)
}

// UnpackDraw returns the seat and tile of a packed draw; an error for a value outside 0 to 543.
func UnpackDraw(packed int) (tile.Seat, tile.TileID, error) {
	if packed < 0 || packed >= seatTileSpace {
		return tile.Seat{}, tile.TileID{}, errors.New("packed draw " + strconv.Itoa(packed) + " out of range")
	}
	seat, _ := tile.NewSeat(packed / tile.TileIDCount)
	id, _ := tile.NewTileID(packed % tile.TileIDCount)
	return seat, id, nil
}

// UnpackDiscard returns the move of a packed discard; an error for a value outside 0 to 2175.
func UnpackDiscard(packed int) (Move, error) {
	if packed < 0 || packed >= discardFlags*seatTileSpace {
		return Move{}, errors.New("packed discard " + strconv.Itoa(packed) + " out of range")
	}
	flags := packed / seatTileSpace
	seat, id, _ := UnpackDraw(packed % seatTileSpace)
	return Move{Seat: seat, Tile: id, Tsumogiri: flags&tsumogiriFlag != 0, Riichi: flags&riichiFlag != 0}, nil
}
