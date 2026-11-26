package record

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func FromStart(seat tile.Seat, events []play.Emitted) (play.SeatRecord, bool) {
	return fromStart(seat, events)
}
