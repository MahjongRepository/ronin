//go:build exhaustive

package hand

import "testing"

const suitShapes = 1953125

func shapeOf(index int) suitCounts {
	var suit suitCounts
	for i := range suit {
		suit[i] = uint8(index % 5)
		index /= 5
	}

	return suit
}

func shapeIndex(suit suitCounts) int {
	index := 0
	for i := len(suit) - 1; i >= 0; i-- {
		index = index*5 + int(suit[i])
	}

	return index
}

func suitMelds() []suitCounts {
	var melds []suitCounts
	for position := range kindsPerSuit {
		var triplet suitCounts
		triplet[position] = 3
		melds = append(melds, triplet)
	}

	for start := range kindsPerSuit - 2 {
		var sequence suitCounts
		sequence[start], sequence[start+1], sequence[start+2] = 1, 1, 1
		melds = append(melds, sequence)
	}

	return melds
}

func markMeldCombinations(suit suitCounts, firstMeld int, melds []suitCounts, meldsOnly []bool) {
	meldsOnly[shapeIndex(suit)] = true
	for index := firstMeld; index < len(melds); index++ {
		combined := suit
		fits := true
		for i := range combined {
			combined[i] += melds[index][i]
			fits = fits && combined[i] <= 4
		}

		if fits {
			markMeldCombinations(combined, index, melds, meldsOnly)
		}
	}
}

func shapesBuiltFromMelds() (meldsOnly, meldsAndPair []bool) {
	meldsOnly = make([]bool, suitShapes)
	markMeldCombinations(suitCounts{}, 0, suitMelds(), meldsOnly)

	meldsAndPair = make([]bool, suitShapes)
	for index, valid := range meldsOnly {
		if !valid {
			continue
		}

		suit := shapeOf(index)
		for position := range suit {
			if suit[position] <= 2 {
				withPair := suit
				withPair[position] += 2
				meldsAndPair[shapeIndex(withPair)] = true
			}
		}
	}

	return meldsOnly, meldsAndPair
}

func TestSuitChecks_WhenEveryShapeIsBuiltFromMelds_ShouldMatchTheReference(t *testing.T) {
	meldsOnly, meldsAndPair := shapesBuiltFromMelds()
	validShapes := 0
	for _, valid := range meldsOnly {
		if valid {
			validShapes++
		}
	}

	if validShapes != 35059 {
		t.Fatalf("reference holds %d melds-only shapes, want 35059", validShapes)
	}

	for index := range suitShapes {
		suit := shapeOf(index)
		if got := isMelds(suit); got != meldsOnly[index] {
			t.Fatalf("isMelds(%v) = %v, want %v", suit, got, meldsOnly[index])
		}

		if got := isMeldsAndPair(suit); got != meldsAndPair[index] {
			t.Fatalf("isMeldsAndPair(%v) = %v, want %v", suit, got, meldsAndPair[index])
		}
	}
}
