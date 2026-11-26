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
	tests := []struct {
		digits string
		want   bool
	}{
		{digits: "11", want: true},
		{digits: "99", want: true},
		{digits: "11123", want: true},
		{digits: "12344", want: true},
		{digits: "11122233344", want: true},
		{digits: "12", want: false},
		{digits: "11223", want: false},
	}
	for _, tc := range tests {
		if got := isMeldsAndPair(suitOf(tc.digits)); got != tc.want {
			t.Errorf("isMeldsAndPair(%q) = %v, want %v", tc.digits, got, tc.want)
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

const (
	copiesPerSuitKind   = 5
	suitCountCombos     = copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind * copiesPerSuitKind
	suitCountSampleStep = 1953
)

func BenchmarkIsMelds(b *testing.B) {
	var suits []suitCounts
	for index := 0; index < suitCountCombos; index += suitCountSampleStep {
		var suit suitCounts
		for i, rest := 0, index; i < kindsPerSuit; i, rest = i+1, rest/copiesPerSuitKind {
			suit[i] = uint8(rest % copiesPerSuitKind)
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
