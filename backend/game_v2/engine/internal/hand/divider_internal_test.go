package hand

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestSuitReadingsOf_WhenSuitIsTheWidest_ShouldFillEveryReadingSlot(t *testing.T) {
	widestSuit := suitCounts{3, 4, 4, 3, 0, 0, 0, 0, 0}

	readings := suitReadingsOf(widestSuit, 0, 2)

	if readings.len != maxSuitReadings {
		t.Errorf("suitReadingsOf gave %d readings, want %d", readings.len, maxSuitReadings)
	}
}

func TestCheckedSub_WhenTheResultWouldGoBelowZero_ShouldRefuse(t *testing.T) {
	tests := []struct {
		kind, n tile.Kind
		want    tile.Kind
		wantOK  bool
	}{
		{0, 0, 0, true},
		{0, 1, 0, false},
		{1, 2, 0, false},
		{1, 1, 0, true},
		{2, 2, 0, true},
		{33, 2, 31, true},
	}
	for _, tc := range tests {
		got, ok := checkedSub(tc.kind, tc.n)
		if got != tc.want || ok != tc.wantOK {
			t.Errorf("checkedSub(%d, %d) = %d, %v; want %d, %v", tc.kind, tc.n, got, ok, tc.want, tc.wantOK)
		}
	}
}
