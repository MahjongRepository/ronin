package score

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

const (
	greenMask uint64 = 1<<19 | 1<<20 | 1<<21 | 1<<23 | 1<<25 | 1<<tile.KindHatsu

	kokushiCountsProduct = 2
	chuurenEndTiles      = 3
)

func isKokushiMusou(counts [tile.KindCount]uint8) bool {
	tiles := 0
	for _, count := range counts {
		tiles += int(count)
	}

	product := 1
	for _, kind := range tile.TerminalAndHonorKinds() {
		product *= int(counts[kind])
	}

	return tiles == winningHandTiles && product == kokushiCountsProduct
}

func countRanks(counts [tile.KindCount]uint8) [suitRanks]int {
	var ranks [suitRanks]int
	for rank := range suitRanks {
		ranks[rank] = int(counts[rank]) + int(counts[suitRanks+rank]) + int(counts[2*suitRanks+rank])
	}

	return ranks
}

func hasChuurenPoutouRanks(counts [tile.KindCount]uint8) bool {
	ranks := countRanks(counts)
	if ranks[0] < chuurenEndTiles || ranks[suitRanks-1] < chuurenEndTiles {
		return false
	}

	ranks[0] -= chuurenEndTiles - 1
	ranks[suitRanks-1] -= chuurenEndTiles - 1
	hasTwoTiles := false
	for _, count := range ranks {
		switch {
		case count == 1:
		case count == 2 && !hasTwoTiles:
			hasTwoTiles = true
		default:
			return false
		}
	}

	return hasTwoTiles
}

func isDaisangen(counts [tile.KindCount]uint8) bool {
	dragons := tile.DragonKinds()
	return countHonorShapes(counts, dragons[:]).sets == dragonCount
}

func isShousuushii(counts [tile.KindCount]uint8) bool {
	winds := tile.WindKinds()
	return countHonorShapes(counts, winds[:]) == honorShapes{sets: shousuushiiSets, pairs: 1}
}

func isDaisuushii(counts [tile.KindCount]uint8) bool {
	winds := tile.WindKinds()
	return countHonorShapes(counts, winds[:]).sets == windCount
}

func isRyuuiisou(kinds uint64) bool {
	return kinds&^greenMask == 0
}

func isTsuuiisou(kinds uint64) bool {
	return kinds&^tile.HonorMask == 0
}

func isChinroutou(kinds uint64) bool {
	return kinds&^tile.TerminalMask == 0
}
