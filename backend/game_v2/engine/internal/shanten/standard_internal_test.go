package shanten

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func kindCounts(t *testing.T, mpsz string) [tile.KindCount]uint8 {
	t.Helper()
	tiles, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	counts, err := tile.CountsFromTiles(tiles)
	if err != nil {
		t.Fatalf("CountsFromTiles(%q) error = %v", mpsz, err)
	}

	return counts.Array()
}

func TestStandardReplacementNumber_WhenHandIsKnown_ShouldCountTheRegularShapeAlone(t *testing.T) {
	tests := []struct {
		hand string
		want int
	}{
		{"19m19p19s1234567z", 9},
		{"119m19p19s1234567z", 8},
		{"123m456p789s1122z", 1},
		{"123m456p789s11222z", 0},
		{"123m456p789s2z", 1},
		{"12389m456p12789s1z", 2},
		{"12389m456p1289s11z", 2},
		{"133345568m23677z", 3},
		{"222345p1234567z", 5},
		{"2344456p123456z", 5},
		{"11222345p12345z", 4},
		{"2234556788p123z", 3},
		{"133345568s11567z", 3},
		{"1111m123p112233s", 2},
		{"1111234444m1111p", 2},
		{"11112222333444z", 2},
		{"1111247777m", 2},
		{"1111247777m1112z", 2},
		{"11114444m", 2},
		{"111124m1111z", 2},
		{"1111444478m", 3},
		{"1111247777m1111z", 2},
		{"1111z", 2},
		{"123m1111z", 2},
		{"11112222z", 2},
		{"123m11p11112222z", 3},
		{"1111m111122233z", 2},
	}
	for _, tc := range tests {
		t.Run(tc.hand, func(t *testing.T) {
			counts := kindCounts(t, tc.hand)
			total := 0
			for _, count := range counts {
				total += int(count)
			}

			if got := standardReplacementNumber(counts, total/tilesPerSet); got != tc.want {
				t.Errorf("standardReplacementNumber(%s) = %d, want %d", tc.hand, got, tc.want)
			}
		})
	}
}

func TestUnpackReplacementNumber_ShouldReadTheNumberOfEachPairAndSetCount(t *testing.T) {
	pack := uint32(1<<2 | 4<<5 | 7<<9 | 1<<13 | 1<<15 | 3<<18 | 6<<22 | 9<<26)
	want := unpackedNumbers{0, 0, 1, 4, 7, 1, 1, 3, 6, 9}
	if got := unpackReplacementNumber(pack); got != want {
		t.Errorf("unpackReplacementNumber(%#x) = %v, want %v", pack, got, want)
	}
}

func groupCountsUpTo14Tiles(kinds int, yield func([]uint8)) {
	counts := make([]uint8, kinds)
	var fill func(kind, tiles int)
	fill = func(kind, tiles int) {
		if kind == kinds {
			yield(counts)
			return
		}

		for count := 0; count <= tile.CopiesPerKind && tiles+count <= tile.MaxConcealedTiles; count++ {
			counts[kind] = uint8(count)
			fill(kind+1, tiles+count)
		}

		counts[kind] = 0
	}

	fill(0, 0)
}

func TestHash_WhenEveryGroupOfUpTo14TilesIsHashed_ShouldGiveEachItsOwnMapEntry(t *testing.T) {
	tests := []struct {
		name  string
		kinds int
		table [][15][5]uint32
		blob  string
	}{
		{name: "shupai", kinds: 9, table: shupaiHash[:], blob: shupaiReplacementNumbers},
		{name: "zipai", kinds: 7, table: zipaiHash[:], blob: zipaiReplacementNumbers},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if len(tc.blob)%entryBytes != 0 {
				t.Fatalf("map holds %d bytes, not whole entries", len(tc.blob))
			}
			hits := make([]int, len(tc.blob)/entryBytes)
			groupCountsUpTo14Tiles(tc.kinds, func(counts []uint8) {
				h := hash(counts, tc.table)
				if h >= len(hits) {
					t.Fatalf("hash(%v) = %d, past the map's %d entries", counts, h, len(hits))
				}
				hits[h]++
			})
			for h, count := range hits {
				if count != 1 {
					t.Fatalf("map entry %d is hashed to by %d groups, want 1", h, count)
				}
			}
		})
	}
}
