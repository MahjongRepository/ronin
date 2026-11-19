//go:build exhaustive

package hand_test

import (
	"cmp"
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	kindsInSuit                   = 9
	shapesWithSuitPair            = 180387
	shapesWithHonorPair           = 92618
	dividingShapesWithSuitPair    = 18874
	dividingShapesWithHonorPair   = 2869
	sevenPairsShapesWithSuitPair  = 36
	sevenPairsShapesWithHonorPair = 84
	sevenPairsInAHand             = 7
)

type blockShape uint8

const (
	tripletShape blockShape = iota
	pairShape
	sequenceShape
)

type refBlock struct {
	kind  tile.Kind
	shape blockShape
}

func compareRefBlocks(a, b refBlock) int {
	return cmp.Or(cmp.Compare(a.kind, b.kind), cmp.Compare(a.shape, b.shape))
}

type suitShape [kindsInSuit]uint8

func everySuitShapeWithAWinningTileCount() []suitShape {
	var shapes []suitShape
	var collect func(counts suitShape, kind, total int)
	collect = func(counts suitShape, kind, total int) {
		if kind == kindsInSuit {
			if total%3 != 1 {
				shapes = append(shapes, counts)
			}
			return
		}
		for count := 0; count <= min(tile.CopiesPerKind, tile.MaxConcealedTiles-total); count++ {
			next := counts
			next[kind] = uint8(count)
			collect(next, kind+1, total+count)
		}
	}
	collect(suitShape{}, 0, 0)
	return shapes
}

func needsHonorPair(counts suitShape) bool {
	sum := 0
	for _, count := range counts {
		sum += int(count)
	}
	return sum%3 == 0
}

func splitIntoSets(counts suitShape) [][]refBlock {
	lowest := slices.IndexFunc(counts[:], func(count uint8) bool { return count > 0 })
	if lowest < 0 {
		return [][]refBlock{{}}
	}

	var splits [][]refBlock
	if counts[lowest] >= 3 {
		rest := counts
		rest[lowest] -= 3
		splits = append(splits, prependSet(refBlock{tile.Kind(lowest), tripletShape}, rest)...)
	}
	if lowest+2 < kindsInSuit && counts[lowest+1] > 0 && counts[lowest+2] > 0 {
		rest := counts
		rest[lowest]--
		rest[lowest+1]--
		rest[lowest+2]--
		splits = append(splits, prependSet(refBlock{tile.Kind(lowest), sequenceShape}, rest)...)
	}
	return splits
}

func prependSet(set refBlock, rest suitShape) [][]refBlock {
	var splits [][]refBlock
	for _, sets := range splitIntoSets(rest) {
		splits = append(splits, append([]refBlock{set}, sets...))
	}
	return splits
}

func sortedReading(blocks []refBlock, extra ...refBlock) []refBlock {
	reading := append(slices.Clone(blocks), extra...)
	slices.SortFunc(reading, compareRefBlocks)
	return reading
}

func bruteForceManReadings(counts suitShape) [][]refBlock {
	var readings [][]refBlock
	honorPair := []refBlock{}
	if needsHonorPair(counts) {
		honorPair = []refBlock{{tile.KindEast, pairShape}}
		for _, sets := range splitIntoSets(counts) {
			readings = append(readings, sortedReading(sets, honorPair...))
		}
	} else {
		for pair, count := range counts {
			if count < 2 {
				continue
			}
			rest := counts
			rest[pair] -= 2
			for _, sets := range splitIntoSets(rest) {
				readings = append(readings, sortedReading(sets, refBlock{tile.Kind(pair), pairShape}))
			}
		}
	}

	var suitPairs []refBlock
	onlyPairs := true
	for kind, count := range counts {
		onlyPairs = onlyPairs && (count == 0 || count == 2)
		if count == 2 {
			suitPairs = append(suitPairs, refBlock{tile.Kind(kind), pairShape})
		}
	}
	if onlyPairs && len(suitPairs)+len(honorPair) == sevenPairsInAHand {
		readings = append(readings, sortedReading(suitPairs, honorPair...))
	}

	slices.SortFunc(readings, func(a, b []refBlock) int { return slices.CompareFunc(a, b, compareRefBlocks) })
	return slices.CompactFunc(readings, slices.Equal)
}

func shiftedToSuit(readings [][]refBlock, suitStart tile.Kind) [][]refBlock {
	shifted := make([][]refBlock, 0, len(readings))
	for _, reading := range readings {
		blocks := make([]refBlock, 0, len(reading))
		for _, b := range reading {
			if b.kind != tile.KindEast {
				b.kind += suitStart
			}
			blocks = append(blocks, b)
		}
		shifted = append(shifted, blocks)
	}
	return shifted
}

func blockOfKinds(kinds []tile.Kind) (refBlock, bool) {
	switch {
	case len(kinds) == 2 && kinds[0] == kinds[1]:
		return refBlock{kinds[0], pairShape}, true
	case len(kinds) == 3 && kinds[0] == kinds[1] && kinds[1] == kinds[2]:
		return refBlock{kinds[0], tripletShape}, true
	case len(kinds) == 3 && kinds[1] == kinds[0]+1 && kinds[2] == kinds[0]+2:
		return refBlock{kinds[0], sequenceShape}, true
	default:
		return refBlock{}, false
	}
}

func readingOfKindSets(d hand.Decomposition) ([]refBlock, bool) {
	var blocks []refBlock
	for _, kinds := range d.KindSets() {
		b, ok := blockOfKinds(kinds)
		if !ok {
			return nil, false
		}
		blocks = append(blocks, b)
	}
	return blocks, true
}

func typedReadingMatches(d hand.Decomposition, reading []refBlock) bool {
	var pairs []tile.Kind
	var sets []hand.Set
	for _, b := range reading {
		switch b.shape {
		case pairShape:
			pairs = append(pairs, b.kind)
		case tripletShape:
			sets = append(sets, hand.Set{Shape: hand.Triplet, Kind: b.kind})
		case sequenceShape:
			sets = append(sets, hand.Set{Shape: hand.Sequence, Kind: b.kind})
		}
	}

	if sevenPairs, ok := d.SevenPairs(); ok {
		return len(pairs) == sevenPairsInAHand && slices.Equal(sevenPairs[:], pairs)
	}
	setsAndPair, _ := d.SetsAndPair()
	return len(pairs) == 1 && setsAndPair.Pair() == pairs[0] && slices.Equal(setsAndPair.Sets(), sets)
}

func countsInSuit(counts suitShape, suitStart tile.Kind) [tile.KindCount]uint8 {
	var all [tile.KindCount]uint8
	copy(all[suitStart:], counts[:])
	if needsHonorPair(counts) {
		all[tile.KindEast] = 2
	}
	return all
}

func isSevenPairsReading(reading []refBlock) bool {
	pairs := 0
	for _, b := range reading {
		if b.shape == pairShape {
			pairs++
		}
	}
	return pairs == sevenPairsInAHand
}

func countShapesRead(cases []shapeCase, sevenPairs bool) int {
	shapes := 0
	for _, c := range cases {
		if slices.ContainsFunc(c.manReadings, func(r []refBlock) bool { return isSevenPairsReading(r) == sevenPairs }) {
			shapes++
		}
	}
	return shapes
}

type shapeCase struct {
	counts      suitShape
	manReadings [][]refBlock
}

func TestDivide_WhenEverySingleSuitShapeIsSplitByBruteForce_ShouldGiveTheSameReadings(t *testing.T) {
	var withSuitPair, withHonorPair []shapeCase
	for _, counts := range everySuitShapeWithAWinningTileCount() {
		c := shapeCase{counts, bruteForceManReadings(counts)}
		if needsHonorPair(counts) {
			withHonorPair = append(withHonorPair, c)
		} else {
			withSuitPair = append(withSuitPair, c)
		}
	}
	for name, got := range map[string][2]int{
		"shapes with a suit pair":               {len(withSuitPair), shapesWithSuitPair},
		"shapes with an honor pair":             {len(withHonorPair), shapesWithHonorPair},
		"dividing shapes with a suit pair":      {countShapesRead(withSuitPair, false), dividingShapesWithSuitPair},
		"dividing shapes with an honor pair":    {countShapesRead(withHonorPair, false), dividingShapesWithHonorPair},
		"seven-pairs shapes with a suit pair":   {countShapesRead(withSuitPair, true), sevenPairsShapesWithSuitPair},
		"seven-pairs shapes with an honor pair": {countShapesRead(withHonorPair, true), sevenPairsShapesWithHonorPair},
	} {
		if got[0] != got[1] {
			t.Fatalf("%s = %d, want %d", name, got[0], got[1])
		}
	}

	mismatches := 0
	for _, suitStart := range tile.SuitStarts() {
		for _, c := range slices.Concat(withSuitPair, withHonorPair) {
			if !dividesAsTheReference(t, c, suitStart) {
				mismatches++
			}
		}
	}
	if mismatches > 0 {
		t.Errorf("%d mismatches", mismatches)
	}
}

func dividesAsTheReference(t *testing.T, c shapeCase, suitStart tile.Kind) bool {
	t.Helper()
	want := shiftedToSuit(c.manReadings, suitStart)
	decompositions, err := hand.Divide(mustCountsFromArray(t, countsInSuit(c.counts, suitStart)))
	if err != nil {
		t.Fatalf("Divide(%v at %d) error = %v", c.counts, suitStart, err)
	}

	got := slices.Collect(decompositions.All())
	matches := len(got) == len(want)
	for i := 0; matches && i < len(got); i++ {
		blocks, ok := readingOfKindSets(got[i])
		matches = ok && slices.Equal(blocks, want[i]) && typedReadingMatches(got[i], want[i])
	}
	if !matches {
		t.Errorf("Divide(%v at %d) = %v, want %v", c.counts, suitStart, got, want)
	}
	return matches
}
