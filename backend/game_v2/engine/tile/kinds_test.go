package tile_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestKinds_WhenKindsAreAdded_ShouldHoldEachOnceLowestFirst(t *testing.T) {
	var empty tile.Kinds
	kinds := empty.With(30).With(3).With(30)
	if !empty.IsEmpty() || kinds.IsEmpty() {
		t.Errorf("IsEmpty = %v for the empty set, %v after With", empty.IsEmpty(), kinds.IsEmpty())
	}

	if got := slices.Collect(kinds.All()); !slices.Equal(got, []tile.Kind{3, 30}) || kinds.Len() != 2 {
		t.Errorf("All = %v, Len = %d; want [3 30], 2", got, kinds.Len())
	}

	if !kinds.Contains(3) || kinds.Contains(4) {
		t.Errorf("Contains(3) = %v, Contains(4) = %v", kinds.Contains(3), kinds.Contains(4))
	}
}

func TestKindsContains_WhenKindIsPast63_ShouldBeFalse(t *testing.T) {
	full := tile.KindsFromBits(^uint64(0))
	for _, kind := range []tile.Kind{64, 65, 255} {
		if full.Contains(kind) {
			t.Errorf("Contains(%d) = true", kind)
		}
	}

	if !full.Contains(63) {
		t.Error("Contains(63) = false")
	}
}

func TestKindsDifference_ShouldKeepTheKindsNotInTheOther(t *testing.T) {
	kinds := tile.KindsFromBits(tile.Mask(1, 2, 3))
	got := slices.Collect(kinds.Difference(tile.KindsFromBits(tile.Mask(2, 5))).All())
	if !slices.Equal(got, []tile.Kind{1, 3}) {
		t.Errorf("Difference = %v, want [1 3]", got)
	}
}

func TestKindsAll_WhenTheCallerStops_ShouldYieldNoMore(t *testing.T) {
	var got []tile.Kind
	for kind := range tile.KindsFromBits(tile.Mask(7, 9)).All() {
		got = append(got, kind)
		break
	}
	if !slices.Equal(got, []tile.Kind{7}) {
		t.Errorf("first kind = %v, want [7]", got)
	}
}
