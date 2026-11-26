package score

import (
	"fmt"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestIsTanyao_WhenTheHandHoldsTerminalsOrHonors_ShouldReject(t *testing.T) {
	for _, tc := range []struct {
		mpsz string
		want bool
	}{{"234567m22p234567s", true}, {"234567m22p123456s", false}, {"234567m234567s22z", false}} {
		t.Run(tc.mpsz, func(t *testing.T) {
			if got := isTanyao(kindsOf(t, tc.mpsz)); got != tc.want {
				t.Errorf("isTanyao(%s) = %v, want %v", tc.mpsz, got, tc.want)
			}
		})
	}
}

func TestIsSanshoku_WhenOneSequenceStartsInEverySuit_ShouldAccept(t *testing.T) {
	for _, tc := range []struct {
		mpsz string
		want bool
	}{{"123m12345677p123s", true}, {"23455m123p123456s", false}} {
		t.Run(tc.mpsz, func(t *testing.T) {
			if got := isSanshoku(readingOf(t, tc.mpsz).Sequences); got != tc.want {
				t.Errorf("isSanshoku(%s) = %v, want %v", tc.mpsz, got, tc.want)
			}
		})
	}
}

func TestIsSanshokuDoukou_WhenOneTripletKindIsInEverySuit_ShouldAccept(t *testing.T) {
	for _, tc := range []struct {
		mpsz string
		want bool
	}{{"111m11145677p111s", true}, {"222m33344455p111s", false}, {"23455m111p111s111z", false}} {
		t.Run(tc.mpsz, func(t *testing.T) {
			if got := isSanshokuDoukou(readingOf(t, tc.mpsz).Triplets); got != tc.want {
				t.Errorf("isSanshokuDoukou(%s) = %v, want %v", tc.mpsz, got, tc.want)
			}
		})
	}
}

func TestIsToitoi_WhenEverySetIsATriplet_ShouldAccept(t *testing.T) {
	for _, mpsz := range []string{"333m44555p111333s", "777888999p777s44z"} {
		t.Run(mpsz, func(t *testing.T) {
			if !isToitoi(readingOf(t, mpsz).Triplets) {
				t.Errorf("isToitoi(%s) = false, want true", mpsz)
			}
		})
	}
}

func TestIsHonroutou_WhenEveryTileIsATerminalOrHonor_ShouldAccept(t *testing.T) {
	for _, mpsz := range []string{"111m111999s11222z", "1199m11p22334466z"} {
		t.Run(mpsz, func(t *testing.T) {
			if !isHonroutou(kindsOf(t, mpsz)) {
				t.Errorf("isHonroutou(%s) = false, want true", mpsz)
			}
		})
	}
}

func TestCountClosedTriplets_WhenARonCompletesATriplet_ShouldCountItOpenAndNotForAChi(t *testing.T) {
	reading := readingOf(t, "444m777p222234s55z")
	twoSou := kindOf(t, "2s")
	triplet := hand.SetWinBlock(hand.Set{Shape: hand.Triplet, Kind: twoSou})
	sequence := hand.SetWinBlock(hand.Set{Shape: hand.Sequence, Kind: twoSou})
	for _, tc := range []struct {
		block hand.WinBlock
		tsumo bool
		want  int
	}{{triplet, false, 2}, {sequence, false, 3}, {triplet, true, 3}} {
		t.Run(fmt.Sprintf("%v tsumo %t", tc.block, tc.tsumo), func(t *testing.T) {
			if got := countClosedTriplets(reading, tc.block, tc.tsumo); got != tc.want {
				t.Errorf("countClosedTriplets(%v, tsumo %v) = %d, want %d", tc.block, tc.tsumo, got, tc.want)
			}
		})
	}
}

func TestCountClosedTriplets_WhenAMeldIsDeclared_ShouldCountAClosedKanAndNotAnOpenKanOrPon(t *testing.T) {
	sequence := hand.SetWinBlock(hand.Set{Shape: hand.Sequence, Kind: kindOf(t, "2s")})
	for _, tc := range []struct {
		meld meld.Meld
		want int
	}{
		{newMeld(t, meld.ClosedKan, "1111m"), 3},
		{newMeld(t, meld.OpenKan, "1111m"), 2},
		{newMeld(t, meld.Pon, "111m"), 2},
	} {
		t.Run(tc.meld.String(), func(t *testing.T) {
			reading := readingOf(t, "444m777p234s55z", tc.meld)
			if got := countClosedTriplets(reading, sequence, true); got != tc.want {
				t.Errorf("countClosedTriplets(with %v) = %d, want %d", tc.meld, got, tc.want)
			}
		})
	}
}

func TestIsShousangen_WhenTwoDragonSetsAndADragonPair_ShouldAccept(t *testing.T) {
	if !isShousangen(countsOf(t, "345m123s55666777z")) {
		t.Error("isShousangen(345m123s55666777z) = false, want true")
	}
	if isShousangen(countsOf(t, "22m123s555666777z")) {
		t.Error("isShousangen(22m123s555666777z) = true, want false")
	}
}

func TestIsChantaShape_WhenEverySetAndThePairHoldATerminalOrHonorWithASequence_ShouldAccept(t *testing.T) {
	for _, tc := range []struct {
		mpsz string
		want bool
	}{
		{"123789m123s22333z", true},
		{"123789m12399p789s", true},
		{"111999m111s22333z", false},
		{"111999m11p111999s", false},
	} {
		t.Run(tc.mpsz, func(t *testing.T) {
			if got := isChantaShape(readingOf(t, tc.mpsz)); got != tc.want {
				t.Errorf("isChantaShape(%s) = %v, want %v", tc.mpsz, got, tc.want)
			}
		})
	}
}

func TestIsIttsu_WhenOneSuitHoldsOneToNine_ShouldAccept(t *testing.T) {
	for _, tc := range []struct {
		mpsz string
		want bool
	}{{"123456789m123s22z", true}, {"112233456789m22z", true}, {"122334567789m11z", false}} {
		t.Run(tc.mpsz, func(t *testing.T) {
			if got := isIttsu(readingOf(t, tc.mpsz).Sequences); got != tc.want {
				t.Errorf("isIttsu(%s) = %v, want %v", tc.mpsz, got, tc.want)
			}
		})
	}
}

func TestHasHonorSet_WhenTheHandHoldsAnHonorTriplet_ShouldFindIt(t *testing.T) {
	for _, tc := range []struct {
		honor string
		kind  tile.Kind
	}{{"555", tile.KindHaku}, {"666", tile.KindHatsu}, {"777", tile.KindChun}} {
		t.Run(tc.honor, func(t *testing.T) {
			if !hasHonorSet(countsOf(t, "23422m234567s"+tc.honor+"z"), tc.kind) {
				t.Errorf("hasHonorSet(%sz) = false, want true", tc.honor)
			}
		})
	}
}

func TestIsSeatWind_WhenTheHandHoldsASetOfTheSeatWind_ShouldAccept(t *testing.T) {
	for _, wind := range []tile.Wind{tile.East, tile.South, tile.West, tile.North} {
		t.Run(fmt.Sprint(wind), func(t *testing.T) {
			digit := wind.Tile().String()[:1]
			mpsz := "23422m234567s" + digit + digit + digit + "z"
			if !isSeatWind(countsOf(t, mpsz), wind.Kind(), wind) {
				t.Errorf("isSeatWind(%s, %v) = false, want true", mpsz, wind)
			}
		})
	}
}

func TestIsSeatWindAndIsRoundWind_WhenTheWindIsNotTheSeatOrRoundWind_ShouldReject(t *testing.T) {
	counts := countsOf(t, "23422m234567s222z")
	for _, tc := range []struct {
		name string
		got  bool
		want bool
	}{
		{"south set, seat east", isSeatWind(counts, tile.KindSouth, tile.East), false},
		{"no east set, seat east", isSeatWind(counts, tile.KindEast, tile.East), false},
		{"south set, round south", isRoundWind(counts, tile.KindSouth, tile.South), true},
		{"south set, round east", isRoundWind(counts, tile.KindSouth, tile.East), false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if tc.got != tc.want {
				t.Errorf("wind yaku = %v, want %v", tc.got, tc.want)
			}
		})
	}
}
