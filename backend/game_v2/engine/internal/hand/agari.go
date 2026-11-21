// Package hand reads the concealed tiles of a hand: whether they are complete (agari), every way
// a winning hand splits into sets and a pair or seven pairs (the divider), and the formal waits
// and the discards that keep a hand tenpai. Yaku and scoring stay out.
//
// An opt-in exhaustive check compares the suit walk and the divider with brute-force references
// over every single-suit shape:
//
//	go test -tags exhaustive -run 'TestSuitChecks|TestDivide_WhenEverySingleSuit' ./engine/internal/hand
package hand

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

const (
	kindsPerSuit = 9
	blockTiles   = 3
	setTiles     = 3
)

type suitCounts = [kindsPerSuit]uint8

// IsAgari reports whether the tiles form a complete hand: zero to four sets plus one pair, seven
// different pairs, or thirteen orphans. Pass only the concealed tiles; the tiles of declared melds
// stay out. A hand of more than 14 tiles is never complete.
func IsAgari(c tile.Counts) bool {
	return isAgari(c.Array())
}

func isAgari(counts [tile.KindCount]uint8) bool {
	if total(counts) > tile.MaxConcealedTiles {
		return false
	}

	honors := counts[tile.HonorStart:]
	var honorCountsSeen uint8
	for _, count := range honors {
		honorCountsSeen |= 1 << count
	}
	someHonorMissing := honorCountsSeen&(1<<0) != 0
	someHonorSingle := honorCountsSeen&(1<<1) != 0
	someHonorTriplet := honorCountsSeen&(1<<3) != 0
	someHonorQuad := honorCountsSeen&(1<<4) != 0

	if someHonorQuad {
		return false
	}
	if someHonorSingle {
		return !someHonorMissing && isThirteenOrphans(counts)
	}
	if !someHonorTriplet && isSevenPairs(counts) {
		return true
	}

	suits := suitsOf(counts)
	remainders := suitRemainders(suits)
	if !isOnePairSplit(remainders, honors) {
		return false
	}
	for i, suit := range suits {
		if !isSuitComplete(suit, remainders[i]) {
			return false
		}
	}
	return true
}

func isSuitComplete(suit suitCounts, remainder int) bool {
	if remainder == 2 {
		return isMeldsAndPair(suit)
	}
	return weightedRemainder(suit) == 0 && isMelds(suit)
}

func total(counts [tile.KindCount]uint8) int {
	sum := 0
	for _, count := range counts {
		sum += int(count)
	}
	return sum
}

func suitsOf(counts [tile.KindCount]uint8) [3]suitCounts {
	var suits [3]suitCounts
	for i, start := range tile.SuitStarts() {
		suits[i] = suitCounts(counts[start : start+kindsPerSuit])
	}
	return suits
}

func suitRemainders(suits [3]suitCounts) [3]int {
	var remainders [3]int
	for i, suit := range suits {
		sum := 0
		for _, count := range suit {
			sum += int(count)
		}
		remainders[i] = sum % setTiles
	}
	return remainders
}

func isOnePairSplit(remainders [3]int, honors []uint8) bool {
	pairs := 0
	for _, remainder := range remainders {
		if remainder == 1 {
			return false
		}
		if remainder == 2 {
			pairs++
		}
	}
	for _, count := range honors {
		if count == 2 {
			pairs++
		}
	}
	return pairs == 1
}

func isThirteenOrphans(counts [tile.KindCount]uint8) bool {
	product := 1
	for _, kind := range tile.TerminalAndHonorKinds() {
		product *= int(counts[kind])
	}
	return product == 2
}

func isSevenPairs(counts [tile.KindCount]uint8) bool {
	pairs := 0
	for _, count := range counts {
		if count == 2 {
			pairs++
		}
	}
	return pairs == sevenPairs
}

func weightedRemainder(suit suitCounts) int {
	weights := [blockTiles]int{1, 2, 0}
	sum := 0
	for i, count := range suit {
		sum += int(count) * weights[i%blockTiles]
	}
	return sum % setTiles
}

func pairOffset(suit suitCounts) int {
	switch weightedRemainder(suit) {
	case 0:
		return 2
	case 1:
		return 1
	default:
		return 0
	}
}

func isMeldsAndPair(suit suitCounts) bool {
	for at := pairOffset(suit); at < kindsPerSuit; at += blockTiles {
		if suit[at] < 2 {
			continue
		}
		rest := suit
		rest[at] -= 2
		if isMelds(rest) {
			return true
		}
	}
	return false
}

func isMelds(suit suitCounts) bool {
	var twoBack, oneBack uint8
	for _, count := range suit {
		open := twoBack + oneBack
		if count < open {
			return false
		}
		twoBack, oneBack = oneBack, (count-open)%setTiles
	}
	return twoBack == 0 && oneBack == 0
}
