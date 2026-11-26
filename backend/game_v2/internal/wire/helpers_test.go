package wire

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func seatOf(t *testing.T, n int) tile.Seat {
	t.Helper()
	seat, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("seat %d out of range", n)
	}

	return seat
}

func tileIDOf(t *testing.T, n int) tile.TileID {
	t.Helper()
	id, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("tile id %d out of range", n)
	}

	return id
}
