package hand

import (
	"testing"
)

func suitOf(digits string) suitCounts {
	var suit suitCounts
	for _, digit := range digits {
		suit[digit-'1']++
	}
	return suit
}

func TestIsMelds_WhenSuitIsSequencesAndTriplets_ShouldAccept(t *testing.T) {
	for _, digits := range []string{"", "123", "111", "111222333", "112233", "111123", "789"} {
		if !isMelds(suitOf(digits)) {
			t.Errorf("isMelds(%q) = false, want true", digits)
		}
	}
}

func TestIsMelds_WhenTilesAreLeftOver_ShouldReject(t *testing.T) {
	for _, digits := range []string{"1", "12", "124", "89", "1234"} {
		if isMelds(suitOf(digits)) {
			t.Errorf("isMelds(%q) = true, want false", digits)
		}
	}
}

func TestIsMeldsAndPair_WhenSuitHoldsAPair_ShouldFindIt(t *testing.T) {
	for digits, want := range map[string]bool{
		"11":          true,
		"99":          true,
		"11123":       true,
		"12344":       true,
		"11122233344": true,
		"12":          false,
		"11223":       false,
	} {
		if got := isMeldsAndPair(suitOf(digits)); got != want {
			t.Errorf("isMeldsAndPair(%q) = %v, want %v", digits, got, want)
		}
	}
}

func TestWeightedRemainder_WhenSuitIsMeldsOnly_ShouldBeZero(t *testing.T) {
	for _, digits := range []string{"123", "456", "789", "111", "555", "999", "123456789"} {
		if got := weightedRemainder(suitOf(digits)); got != 0 {
			t.Errorf("weightedRemainder(%q) = %d, want 0", digits, got)
		}
	}
}

func BenchmarkIsMelds(b *testing.B) {
	var suits []suitCounts
	for index := 0; index < 5*5*5*5*5*5*5*5*5; index += 1953 {
		var suit suitCounts
		for i, rest := 0, index; i < kindsPerSuit; i, rest = i+1, rest/5 {
			suit[i] = uint8(rest % 5)
		}
		suits = append(suits, suit)
	}
	melds := 0
	for b.Loop() {
		for _, suit := range suits {
			if isMelds(suit) {
				melds++
			}
		}
	}
	b.ReportMetric(float64(melds)/float64(b.N), "melds/op")
}
