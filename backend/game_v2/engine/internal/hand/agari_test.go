package hand_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestIsAgari_WhenHandIsSetsAndAPair_ShouldBeComplete(t *testing.T) {
	for _, mpsz := range []string{
		"123456789s11123p",
		"123456789p11123m",
		"123456789m11122z",
		"234567m234567p22s",
		"112233m456p789s55z",
		"11122233344455m",
		"11123456789999m",
		"111222333m11122z",
		"11222333444m555z",
		"123m123m123m123m11z",
		"11m",
		"22z",
		"11123m",
	} {
		if !hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = false, want true", mpsz)
		}
	}
}

func TestIsAgari_WhenHandIsIncomplete_ShouldNotBeComplete(t *testing.T) {
	for _, mpsz := range []string{
		"123456789s12345p",
		"111222444m11145z",
		"11223344556678m",
		"123456789m11123z",
		"123456789m1234z",
		"11122233344457m",
		"111m",
		"12m",
		"",
		"11m22p",
		"111122223334m11z",
	} {
		if hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = true, want false", mpsz)
		}
	}
}

func TestIsAgari_WhenHandIsSevenDifferentPairs_ShouldBeComplete(t *testing.T) {
	for _, mpsz := range []string{"1133557799m1122p", "1199m1199p1199s11z", "1122334455m6677z"} {
		if !hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = false, want true", mpsz)
		}
	}
}

func TestIsAgari_WhenTwoPairsAreOfOneKind_ShouldNotBeSevenPairs(t *testing.T) {
	for _, mpsz := range []string{"1111335577m1122p", "1133557799m1111z"} {
		if hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = true, want false", mpsz)
		}
	}
}

func TestIsAgari_WhenHandIsThirteenOrphans_ShouldBeComplete(t *testing.T) {
	for _, mpsz := range []string{"19m19p19s11234567z", "119m19p19s1234567z"} {
		if !hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = false, want true", mpsz)
		}
	}
}

func TestIsAgari_WhenATerminalOrHonorIsMissing_ShouldNotBeThirteenOrphans(t *testing.T) {
	for _, mpsz := range []string{"19m19p19s12234567z1m", "19m19p11s11234567z"} {
		if hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = true, want false", mpsz)
		}
	}
}

func TestIsAgari_WhenTheConcealedPartHoldsAnHonorQuad_ShouldNotBeComplete(t *testing.T) {
	if hand.IsAgari(mustCounts(t, "123456789m1111z11p")) {
		t.Error("IsAgari(123456789m1111z11p) = true, want false")
	}
}

func TestIsAgari_WhenHandHoldsMoreThan14Tiles_ShouldNotBeComplete(t *testing.T) {
	for _, mpsz := range []string{
		"19m19p19s11234567z5m",
		"19m19p19s11234567z56m",
		"19m19p19s11234567z567m",
		"1133557799m1122p4s",
		"1133557799m1122p46s",
		"1133557799m1122p468s",
		"123456789m123p456s11z",
	} {
		if hand.IsAgari(mustCounts(t, mpsz)) {
			t.Errorf("IsAgari(%s) = true, want false", mpsz)
		}
	}
}

func BenchmarkIsAgari(b *testing.B) {
	hands := []tile.Counts{
		mustCounts(b, "123456789s11123p"),
		mustCounts(b, "11122233344455m"),
		mustCounts(b, "234567m234567p22s"),
		mustCounts(b, "123456789m11123z"),
		mustCounts(b, "11223344556678m"),
		mustCounts(b, "1133557799m1122p"),
		mustCounts(b, "19m19p19s11234567z"),
	}

	complete := 0
	for b.Loop() {
		for _, counts := range hands {
			if hand.IsAgari(counts) {
				complete++
			}
		}
	}

	b.ReportMetric(float64(complete)/float64(b.N), "complete/op")
}
