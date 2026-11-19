package score

import (
	"math/bits"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	manMask                         uint64 = 0x1FF
	ittsuStarts                     uint64 = 1<<0 | 1<<3 | 1<<6
	terminalSequenceStarts          uint64 = 1<<0 | 1<<6 | 1<<9 | 1<<15 | 1<<18 | 1<<24
	honorSetTiles                          = 3
	honorPairTiles                         = 2
	toitoiTriplets                         = 4
	suitsSpan                              = 9
	lastSuitStartOffset                    = 2 * suitsSpan
	shousangenSets, shousuushiiSets        = 2, 3
)

func isTanyao(kinds uint64) bool {
	return kinds&tile.TerminalOrHonorMask == 0
}

func hasHonorSet(counts [tile.KindCount]uint8, honor tile.Kind) bool {
	return counts[honor] >= honorSetTiles
}

func hasHonorPair(counts [tile.KindCount]uint8, honor tile.Kind) bool {
	return counts[honor] == honorPairTiles
}

func isSeatWind(counts [tile.KindCount]uint8, wind tile.Kind, seatWind tile.Wind) bool {
	return seatWind.Kind() == wind && hasHonorSet(counts, wind)
}

func isRoundWind(counts [tile.KindCount]uint8, wind tile.Kind, roundWind tile.Wind) bool {
	return roundWind.Kind() == wind && hasHonorSet(counts, wind)
}

func inEverySuit(kinds uint64) bool {
	return kinds&(kinds>>suitsSpan)&(kinds>>lastSuitStartOffset)&manMask != 0
}

func isSanshoku(sequences uint64) bool {
	return inEverySuit(sequences)
}

func isSanshokuDoukou(triplets uint64) bool {
	return inEverySuit(triplets)
}

func isIttsu(sequences uint64) bool {
	for _, start := range tile.SuitStarts() {
		if sequences>>start&ittsuStarts == ittsuStarts {
			return true
		}
	}
	return false
}

func isChantaShape(reading hand.Reading) bool {
	return !reading.SevenPairs &&
		reading.Sequences != 0 &&
		reading.Sequences&^terminalSequenceStarts == 0 &&
		reading.Triplets&^tile.TerminalOrHonorMask == 0 &&
		reading.Pair.IsTerminalOrHonor()
}

func isHonroutou(kinds uint64) bool {
	return kinds&^tile.TerminalOrHonorMask == 0
}

func isToitoi(triplets uint64) bool {
	return bits.OnesCount64(triplets) == toitoiTriplets
}

func countClosedTriplets(reading hand.Reading, winBlock hand.WinBlock, tsumo bool) int {
	closed := bits.OnesCount64(reading.Triplets &^ reading.OpenTriplets)
	set, isSet := winBlock.Set()
	if !tsumo && isSet && set.Shape == hand.Triplet {
		return closed - 1
	}
	return closed
}

func isShousangen(counts [tile.KindCount]uint8) bool {
	dragons := tile.DragonKinds()
	return countHonorShapes(counts, dragons[:]) == honorShapes{sets: shousangenSets, pairs: 1}
}

type honorShapes struct {
	sets  int
	pairs int
}

func countHonorShapes(counts [tile.KindCount]uint8, honors []tile.Kind) honorShapes {
	var shapes honorShapes
	for _, honor := range honors {
		if hasHonorSet(counts, honor) {
			shapes.sets++
		}
		if hasHonorPair(counts, honor) {
			shapes.pairs++
		}
	}
	return shapes
}
