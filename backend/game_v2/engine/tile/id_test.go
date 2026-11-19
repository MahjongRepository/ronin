package tile_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestTileIDKind_WhenIDIsASuitBoundary_ShouldMapToTheSuitsKind(t *testing.T) {
	var got []tile.Kind
	for _, id := range mustIDs(t, 0, 35, 36, 71, 72, 107, 108, 135, 1, 2, 3) {
		got = append(got, id.Kind())
	}
	want := []tile.Kind{0, 8, 9, 17, 18, 26, 27, 33, 0, 0, 0}
	if !slices.Equal(got, want) {
		t.Errorf("kinds = %v, want %v", got, want)
	}
}

func TestNewTileID_WhenNumberIsNot0To135_ShouldRefuse(t *testing.T) {
	for _, n := range []int{-1, 136, 255, 256 + 5} {
		if _, ok := tile.NewTileID(n); ok {
			t.Errorf("NewTileID(%d) accepted", n)
		}
	}
	if id, ok := tile.NewTileID(135); !ok || id.Index() != 135 {
		t.Errorf("NewTileID(135) = %d, %v; want id 135", id.Index(), ok)
	}
}

func TestAllTileIDs_ShouldListEveryIDInAscendingOrder(t *testing.T) {
	for i, id := range tile.AllTileIDs() {
		if id.Index() != i {
			t.Errorf("AllTileIDs()[%d] = %d", i, id.Index())
		}
	}
}

func TestKindCounts_ShouldCountTheIDsOfEachKind(t *testing.T) {
	counts, err := tile.KindCounts(slices.Values(mustIDs(t, 0, 1, 2, 3, 36, 108, 16, 17)))
	if err != nil {
		t.Fatalf("KindCounts error = %v", err)
	}
	var want [tile.KindCount]uint8
	want[0], want[9], want[27], want[4] = 4, 1, 1, 2
	if got := counts.Array(); got != want {
		t.Errorf("KindCounts = %v, want %v", got, want)
	}
}

func TestKindCounts_WhenAKindHasAFifthCopy_ShouldRefuseIt(t *testing.T) {
	id := mustID(t, 9)
	_, err := tile.KindCounts(slices.Values([]tile.TileID{id, id, id, id, id}))
	if !errors.Is(err, tile.TooManyCopiesError{Kind: 2}) {
		t.Errorf("KindCounts error = %v, want kind 2 too many", err)
	}
}

func TestKindCounts_When256CopiesOfOneID_ShouldRefuseWithoutOverflow(t *testing.T) {
	_, err := tile.KindCounts(slices.Values(slices.Repeat([]tile.TileID{mustID(t, 135)}, 256)))
	if !errors.Is(err, tile.TooManyCopiesError{Kind: 33}) {
		t.Errorf("KindCounts error = %v, want kind 33 too many", err)
	}
}

func TestHeldCopies_ShouldYieldTheCopiesOfTheKindInHandOrder(t *testing.T) {
	hand := mustIDs(t, 18, 3, 17, 40, 16, 19)
	got := slices.Collect(tile.HeldCopies(hand, 4))
	if want := mustIDs(t, 18, 17, 16, 19); !slices.Equal(got, want) {
		t.Errorf("HeldCopies = %v, want %v", got, want)
	}
}

func TestHeldCopies_WhenTheCallerStops_ShouldYieldNoMore(t *testing.T) {
	hand := mustIDs(t, 18, 17, 16)
	var got []tile.TileID
	for id := range tile.HeldCopies(hand, 4) {
		got = append(got, id)
		break
	}
	if want := mustIDs(t, 18); !slices.Equal(got, want) {
		t.Errorf("first held copy = %v, want %v", got, want)
	}
}
