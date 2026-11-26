package hand_test

import (
	"errors"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestDivide_WhenHandHasOneReading_ShouldSplitItIntoSetsAndThePair(t *testing.T) {
	tests := []struct {
		mpsz string
		want []string
	}{
		{mpsz: "234567m23455s777z", want: []string{"234m", "567m", "234s", "55s", "777z"}},
		{mpsz: "123m123p123s11222z", want: []string{"123m", "123p", "123s", "11z", "222z"}},
		{mpsz: "23444m344556p333s", want: []string{"234m", "44m", "345p", "456p", "333s"}},
		{mpsz: "111123666789s11z", want: []string{"111s", "123s", "666s", "789s", "11z"}},
	}
	for _, tc := range tests {
		t.Run(tc.mpsz, func(t *testing.T) {
			got := mustDivide(t, tc.mpsz)
			if len(got) != 1 || !slices.Equal(setsMpsz(t, got[0]), tc.want) {
				t.Errorf("Divide(%s) = %d readings, first %v; want one, %v", tc.mpsz, len(got), setsMpsz(t, got[0]), tc.want)
			}
		})
	}
}

func TestDivide_WhenHandHasTwoReadings_ShouldSortThem(t *testing.T) {
	tests := []struct {
		mpsz string
		want [2][]string
	}{
		{
			mpsz: "11122233388899m",
			want: [2][]string{
				{"111m", "222m", "333m", "888m", "99m"},
				{"123m", "123m", "123m", "888m", "99m"},
			},
		},
		{
			mpsz: "112233m99p445566s",
			want: [2][]string{
				{"11m", "22m", "33m", "99p", "44s", "55s", "66s"},
				{"123m", "123m", "99p", "456s", "456s"},
			},
		},
	}
	for _, tc := range tests {
		t.Run(tc.mpsz, func(t *testing.T) {
			got := mustDivide(t, tc.mpsz)
			if len(got) != 2 {
				t.Fatalf("Divide(%s) gave %d readings, want 2", tc.mpsz, len(got))
			}

			for i := range got {
				if sets := setsMpsz(t, got[i]); !slices.Equal(sets, tc.want[i]) {
					t.Errorf("Divide(%s)[%d] = %v, want %v", tc.mpsz, i, sets, tc.want[i])
				}
			}
		})
	}
}

func TestDivide_WhenReadingsSplitAcrossSuits_ShouldSortSevenPairsAmongThem(t *testing.T) {
	want := [][]string{
		{"55m", "66m", "77m", "11p", "22p", "33p", "44p"},
		{"567m", "567m", "11p", "234p", "234p"},
		{"567m", "567m", "123p", "123p", "44p"},
	}

	got := mustDivide(t, "556677m11223344p")
	if len(got) != len(want) {
		t.Fatalf("Divide gave %d readings, want %d", len(got), len(want))
	}

	for i := range got {
		if sets := setsMpsz(t, got[i]); !slices.Equal(sets, want[i]) {
			t.Errorf("reading %d = %v, want %v", i, sets, want[i])
		}
	}
}

func TestDivide_WhenATripletAndASequenceShareTheLowestKind_ShouldListTheTripletFirst(t *testing.T) {
	want := []hand.Set{
		{Shape: hand.Triplet, Kind: 18},
		{Shape: hand.Sequence, Kind: 18},
		{Shape: hand.Triplet, Kind: 23},
		{Shape: hand.Sequence, Kind: 24},
	}

	got := mustDivide(t, "111123666789s11z")
	if len(got) != 1 {
		t.Fatalf("Divide gave %d readings, want 1", len(got))
	}

	sets, ok := got[0].SetsAndPair()
	if !ok || sets.Pair() != 27 || !slices.Equal(sets.Sets(), want) {
		t.Errorf("reading = %v, pair %d, sets %v; want sets and pair 27, %v", ok, sets.Pair(), sets.Sets(), want)
	}
}

func TestDivide_WhenHandReadsAsTripletsOrAsSequences_ShouldTypeThePairAndSets(t *testing.T) {
	want := [][]hand.Set{
		{{Shape: hand.Triplet, Kind: 0}, {Shape: hand.Triplet, Kind: 1}, {Shape: hand.Triplet, Kind: 2}, {Shape: hand.Triplet, Kind: 7}},
		{{Shape: hand.Sequence, Kind: 0}, {Shape: hand.Sequence, Kind: 0}, {Shape: hand.Sequence, Kind: 0}, {Shape: hand.Triplet, Kind: 7}},
	}

	got := mustDivide(t, "11122233388899m")
	if len(got) != len(want) {
		t.Fatalf("Divide gave %d readings, want %d", len(got), len(want))
	}

	for i, d := range got {
		sets, ok := d.SetsAndPair()
		if !ok || sets.Pair() != 8 || !slices.Equal(sets.Sets(), want[i]) {
			t.Errorf("reading %d = %v, pair %d, sets %v; want pair 8, %v", i, ok, sets.Pair(), sets.Sets(), want[i])
		}
	}
}

func TestDivide_WhenHandIsSevenPairs_ShouldReadThePairsInOrder(t *testing.T) {
	want := [7]tile.Kind{0, 8, 10, 16, 20, 24, 27}

	got := mustDivide(t, "1199m2288p3377s11z")
	if len(got) != 1 {
		t.Fatalf("Divide gave %d readings, want 1", len(got))
	}

	pairs, ok := got[0].SevenPairs()
	if !ok || pairs != want {
		t.Errorf("SevenPairs() = %v, %v; want %v, true", pairs, ok, want)
	}

	if _, isSets := got[0].SetsAndPair(); isSets {
		t.Error("SetsAndPair() ok = true for seven pairs")
	}
}

func TestDivide_WhenMeldsTakeSomeTiles_ShouldDivideWhatTheyLeave(t *testing.T) {
	tests := []struct {
		mpsz string
		want []string
	}{
		{mpsz: "11z", want: []string{"11z"}},
		{mpsz: "789p22z", want: []string{"789p", "22z"}},
		{mpsz: "778899p22z", want: []string{"789p", "789p", "22z"}},
		{mpsz: "123m456p55s777z", want: []string{"123m", "456p", "55s", "777z"}},
	}
	for _, tc := range tests {
		t.Run(tc.mpsz, func(t *testing.T) {
			got := mustDivide(t, tc.mpsz)
			if len(got) != 1 || !slices.Equal(setsMpsz(t, got[0]), tc.want) {
				t.Errorf("Divide(%s) = %d readings; want one, %v", tc.mpsz, len(got), tc.want)
			}
		})
	}
}

func TestDivide_WhenHandHoldsFourOfAKind_ShouldReadATripletAndOneMoreTile(t *testing.T) {
	want := []string{"111m", "123m", "55p"}

	got := mustDivide(t, "111123m55p")
	if len(got) != 1 || !slices.Equal(setsMpsz(t, got[0]), want) {
		t.Errorf("Divide = %d readings; want one, %v", len(got), want)
	}
}

func TestDivide_WhenHandDoesNotDivide_ShouldGiveNoReading(t *testing.T) {
	for _, mpsz := range []string{
		"11456m22789p33s44z",
		"234567m2345p678s1z",
		"123456789m11234z",
		"19m19p19s12345677z",
		"2222m88p2288s2244z",
		"124m456p789s11222z",
	} {
		if got := mustDivide(t, mpsz); len(got) != 0 {
			t.Errorf("Divide(%s) gave %d readings, want none", mpsz, len(got))
		}
	}
}

func TestDivide_WhenNoWinningHandHasTheTileCount_ShouldRefuseIt(t *testing.T) {
	tests := []struct {
		mpsz  string
		count int
	}{
		{mpsz: "", count: 0},
		{mpsz: "1m", count: 1},
		{mpsz: "123m", count: 3},
		{mpsz: "123456789m1234z", count: 13},
		{mpsz: "2288m2288p228s2244z", count: 15},
		{mpsz: "123789m123789p111s11z", count: 17},
	}
	for _, tc := range tests {
		t.Run(tc.mpsz, func(t *testing.T) {
			_, err := hand.Divide(mustCounts(t, tc.mpsz))
			if !errors.Is(err, hand.WrongTileCountError{Count: tc.count}) {
				t.Errorf("Divide(%s) error = %v, want a wrong count of %d", tc.mpsz, err, tc.count)
			}
		})
	}
}

func TestWrongTileCountError_ShouldNameTheWinningCounts(t *testing.T) {
	want := "a winning hand has 2, 5, 8, 11 or 14 concealed tiles, not 13"

	if got := (hand.WrongTileCountError{Count: 13}).Error(); got != want {
		t.Errorf("Error() = %q, want %q", got, want)
	}
}

func TestDivide_WhenHandIsAPurePairStraight_ShouldFillEveryReadingSlot(t *testing.T) {
	decompositions, err := hand.Divide(mustCounts(t, "11223344556677m"))
	if err != nil {
		t.Fatalf("Divide error = %v", err)
	}

	var pairs []int
	for d := range decompositions.All() {
		sets, ok := d.SetsAndPair()
		pair := -1
		if ok {
			pair = int(sets.Pair())
		}

		pairs = append(pairs, pair)
	}

	if want := []int{-1, 0, 3, 6}; decompositions.Len() != 4 || !slices.Equal(pairs, want) {
		t.Errorf("Divide = %d readings with pairs %v, want 4 with %v", decompositions.Len(), pairs, want)
	}
}

func TestDecompositionsAll_WhenTheCallerStops_ShouldYieldNoMore(t *testing.T) {
	decompositions, err := hand.Divide(mustCounts(t, "11223344556677m"))
	if err != nil {
		t.Fatalf("Divide error = %v", err)
	}

	yielded := 0
	for range decompositions.All() {
		yielded++
		break
	}

	if yielded != 1 {
		t.Errorf("All yielded %d after a break, want 1", yielded)
	}
}

func TestSetsAndPairSets_ShouldReturnACopy(t *testing.T) {
	sets, _ := mustDivide(t, "123m456p789s11122z")[0].SetsAndPair()

	sets.Sets()[0] = hand.Set{Shape: hand.Triplet, Kind: 33}

	if got := sets.Sets()[0]; got != (hand.Set{Shape: hand.Sequence, Kind: 0}) {
		t.Errorf("Sets()[0] = %v after writing to a returned slice, want 123m", got)
	}
}

func winBlocks(t *testing.T, mpsz, win string) []hand.WinBlock {
	t.Helper()
	decompositions := mustDivide(t, mpsz)
	if len(decompositions) != 1 {
		t.Fatalf("Divide(%s) gave %d readings, want 1", mpsz, len(decompositions))
	}

	return slices.Collect(decompositions[0].WinBlocks(mustKind(t, win)))
}

func TestWinBlocks_WhenTheWinningKindIsThePairAndStartsASequence_ShouldNameThePairFirst(t *testing.T) {
	want := []hand.WinBlock{hand.PairWinBlock(), hand.SetWinBlock(hand.Set{Shape: hand.Sequence, Kind: 4})}

	if got := winBlocks(t, "55567m123p456s777z", "5m"); !slices.Equal(got, want) {
		t.Errorf("WinBlocks(5m) = %v, want %v", got, want)
	}
}

func TestWinBlocks_WhenHandReadsAsSevenPairs_ShouldWinOnThePairOfTheWinningKind(t *testing.T) {
	decompositions := mustDivide(t, "112233m445566p77z")
	if len(decompositions) != 2 {
		t.Fatalf("Divide gave %d readings, want 2", len(decompositions))
	}

	sevenPairs := slices.Collect(decompositions[0].WinBlocks(0))
	sets := slices.Collect(decompositions[1].WinBlocks(0))

	if want := []hand.WinBlock{hand.PairWinBlock()}; !slices.Equal(sevenPairs, want) {
		t.Errorf("seven pairs WinBlocks(1m) = %v, want %v", sevenPairs, want)
	}

	if want := []hand.WinBlock{hand.SetWinBlock(hand.Set{Shape: hand.Sequence, Kind: 0})}; !slices.Equal(sets, want) {
		t.Errorf("sets WinBlocks(1m) = %v, want %v", sets, want)
	}
}

func winBlockKinds(win tile.Kind, block hand.WinBlock) []tile.Kind {
	set, isSet := block.Set()
	switch {
	case !isSet:
		return []tile.Kind{win, win}
	case set.Shape == hand.Sequence:
		return []tile.Kind{set.Kind, set.Kind + 1, set.Kind + 2}
	default:
		return []tile.Kind{set.Kind, set.Kind, set.Kind}
	}
}

func TestWinBlocks_WhenAnyKindWins_ShouldNameEachDistinctBlockOfItInKindSetsOrder(t *testing.T) {
	for _, mpsz := range []string{
		"11122233388899m",
		"11112345678999m",
		"11223344556677m",
		"22233344455566s",
		"112233m445566p77z",
		"123345567m11p789s",
		"11122233344455z",
		"111123m456p789s55z",
		"34555m678p234s777z",
		"123m55p",
		"11m",
	} {
		for _, d := range mustDivide(t, mpsz) {
			for win := range tile.Kind(tile.KindCount) {
				var want [][]tile.Kind
				for _, set := range d.KindSets() {
					if slices.Contains(set, win) && !slices.ContainsFunc(want, func(seen []tile.Kind) bool {
						return slices.Equal(seen, set)
					}) {
						want = append(want, set)
					}
				}

				var got [][]tile.Kind
				for block := range d.WinBlocks(win) {
					got = append(got, winBlockKinds(win, block))
				}

				if !slices.EqualFunc(got, want, slices.Equal) {
					t.Errorf("%s %v WinBlocks(%d) = %v, want %v", mpsz, d.KindSets(), win, got, want)
				}
			}
		}
	}
}

func TestWinBlocks_WhenTheCallerStops_ShouldYieldNoMore(t *testing.T) {
	decompositions := mustDivide(t, "55567m123p456s777z")

	yielded := 0
	for range decompositions[0].WinBlocks(4) {
		yielded++
		break
	}

	if yielded != 1 {
		t.Errorf("WinBlocks yielded %d after a break, want 1", yielded)
	}
}

func TestReading_WhenTwoConcealedSequencesRepeat_ShouldCountIipeikou(t *testing.T) {
	if got := reading(t, "123m23444p112233s", nil, 0).IdenticalSequencePairs; got != 1 {
		t.Errorf("IdenticalSequencePairs = %d, want 1", got)
	}
}

func TestReading_WhenTwoPairsOfSequencesRepeat_ShouldCountRyanpeikou(t *testing.T) {
	for _, mpsz := range []string{"22m223344p112233s", "22m111122223333s"} {
		if got := reading(t, mpsz, nil, 1).IdenticalSequencePairs; got != 2 {
			t.Errorf("%s IdenticalSequencePairs = %d, want 2", mpsz, got)
		}
	}
}

func TestReading_WhenFourIdenticalSequences_ShouldCountTwoPairs(t *testing.T) {
	got := reading(t, "111122223333m55z", nil, 1)

	if got.Sequences != 1 || got.IdenticalSequencePairs != 2 {
		t.Errorf("Sequences = %#x, IdenticalSequencePairs = %d; want 0x1, 2", got.Sequences, got.IdenticalSequencePairs)
	}
}

func TestReading_WhenMeldsArePonsOrKans_ShouldCountOnlyDeclaredKansAsQuads(t *testing.T) {
	pons := []meld.Meld{mustPon(t, "111s"), mustPon(t, "999p"), mustPon(t, "777z")}
	kans := []meld.Meld{mustOpenKan(t, "1111s"), mustClosedKan(t, "9999p"), mustOpenKan(t, "7777z")}
	declared := tile.Mask(18, 17, 33)

	withPons := reading(t, "234m55z", pons, 0)
	withKans := reading(t, "234m55z", kans, 0)

	if withPons.Kans != 0 || withPons.Triplets != declared || withPons.OpenTriplets != declared {
		t.Errorf("with pons = %+v, want no kans and triplets %#x all open", withPons, declared)
	}

	if want := tile.Mask(18, 33); withKans.Kans != declared || withKans.OpenTriplets != want {
		t.Errorf("with kans = %+v, want kans %#x and open triplets %#x", withKans, declared, want)
	}
}

func TestReading_WhenAChiIsDeclared_ShouldAddItsFirstKindToTheSequences(t *testing.T) {
	got := reading(t, "234m11122z", []meld.Meld{mustChi(t, "789p")}, 0)

	want := hand.Reading{Pair: 28, Sequences: tile.Mask(1, 15), Triplets: tile.Mask(27)}
	if got != want {
		t.Errorf("Reading = %+v, want %+v", got, want)
	}
}

func TestReading_WhenHandReadsAsSevenPairs_ShouldHoldNoSets(t *testing.T) {
	got := reading(t, "1199m1199p1199s11z", []meld.Meld{mustPon(t, "777z")}, 0)

	if got != (hand.Reading{SevenPairs: true}) {
		t.Errorf("Reading = %+v, want seven pairs only", got)
	}
}
