package wire

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestPackDraw_ShouldPackTheSeatAndTileIntoOneInteger(t *testing.T) {
	seat := seatOf(t, 3)
	id := tileIDOf(t, 135)

	packed := PackDraw(seat, id)
	unpackedSeat, unpackedTile, err := UnpackDraw(packed)

	if packed != 543 || err != nil || unpackedSeat != seat || unpackedTile != id {
		t.Errorf("PackDraw(3, 135) = %d, unpacked to %v %v %v; want 543 back to 3 135", packed, unpackedSeat, unpackedTile, err)
	}
}

func TestPackDiscard_ShouldPackTheTsumogiriAndRiichiFlagsAboveTheSeatAndTile(t *testing.T) {
	tests := []struct {
		move Move
		want int
	}{
		{Move{Seat: seatOf(t, 2), Tile: tileIDOf(t, 37)}, 309},
		{Move{Seat: seatOf(t, 2), Tile: tileIDOf(t, 37), Tsumogiri: true}, 853},
		{Move{Seat: seatOf(t, 2), Tile: tileIDOf(t, 37), Riichi: true}, 1397},
		{Move{Seat: seatOf(t, 2), Tile: tileIDOf(t, 37), Tsumogiri: true, Riichi: true}, 1941},
	}
	for _, tc := range tests {
		packed := PackDiscard(tc.move)
		unpacked, err := UnpackDiscard(packed)
		if packed != tc.want || err != nil || unpacked != tc.move {
			t.Errorf("PackDiscard(%v) = %d, unpacked to %v %v; want %d back", tc.move, packed, unpacked, err, tc.want)
		}
	}
}

func TestUnpackMove_WhenThePackedValueIsOutOfRange_ShouldRefuseIt(t *testing.T) {
	for _, packed := range []int{-1, tile.SeatCount * tile.TileIDCount} {
		if _, _, err := UnpackDraw(packed); err == nil {
			t.Errorf("UnpackDraw(%d) = nil error, want one", packed)
		}
	}
	for _, packed := range []int{-1, 4 * tile.SeatCount * tile.TileIDCount} {
		if _, err := UnpackDiscard(packed); err == nil {
			t.Errorf("UnpackDiscard(%d) = nil error, want one", packed)
		}
	}
}
