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
		name    string
		kind, n tile.Kind
		want    tile.Kind
		wantOK  bool
	}{
		{name: "zero from zero", kind: 0, n: 0, want: 0, wantOK: true},
		{name: "one below zero", kind: 0, n: 1, want: 0, wantOK: false},
		{name: "two from one", kind: 1, n: 2, want: 0, wantOK: false},
		{name: "one from one", kind: 1, n: 1, want: 0, wantOK: true},
		{name: "two from two", kind: 2, n: 2, want: 0, wantOK: true},
		{name: "two from the last honor", kind: 33, n: 2, want: 31, wantOK: true},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := checkedSub(tc.kind, tc.n)
			if got != tc.want || ok != tc.wantOK {
				t.Errorf("checkedSub(%d, %d) = %d, %v; want %d, %v", tc.kind, tc.n, got, ok, tc.want, tc.wantOK)
			}
		})
	}
}
