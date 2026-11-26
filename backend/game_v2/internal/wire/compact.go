package wire

import (
	"fmt"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const ScoreDivisor = 100

const (
	seatTileSpace = tile.SeatCount * tile.TileIDCount
	discardFlags  = 4
	tsumogiriFlag = 1
	riichiFlag    = 2
)

type Move struct {
	Seat      tile.Seat
	Tile      tile.TileID
	Tsumogiri bool
	Riichi    bool
}

func PackDraw(seat tile.Seat, t tile.TileID) int {
	return seat.Index()*tile.TileIDCount + t.Index()
}

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

func UnpackDraw(packed int) (tile.Seat, tile.TileID, error) {
	if packed < 0 || packed >= seatTileSpace {
		return tile.Seat{}, tile.TileID{}, fmt.Errorf("packed draw %d out of range", packed)
	}

	seat, _ := tile.NewSeat(packed / tile.TileIDCount)
	id, _ := tile.NewTileID(packed % tile.TileIDCount)
	return seat, id, nil
}

func UnpackDiscard(packed int) (Move, error) {
	if packed < 0 || packed >= discardFlags*seatTileSpace {
		return Move{}, fmt.Errorf("packed discard %d out of range", packed)
	}

	flags := packed / seatTileSpace
	seat, id, err := UnpackDraw(packed % seatTileSpace)
	if err != nil {
		return Move{}, err
	}

	return Move{Seat: seat, Tile: id, Tsumogiri: flags&tsumogiriFlag != 0, Riichi: flags&riichiFlag != 0}, nil
}
