package shanten

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

const (
	pairedOffset = 5
	entryBytes   = 4
)

type unpackedNumbers [10]uint32

func standardReplacementNumber(counts [tile.KindCount]uint8, sets int) int {
	numbers := suitNumbers(counts[0:9])
	updateDP(&numbers, suitNumbers(counts[9:18]))
	updateDP(&numbers, suitNumbers(counts[18:27]))
	updateDPFinal(&numbers, honorNumbers(counts[27:34]))
	return int(numbers[pairedOffset+sets])
}

func suitNumbers(counts []uint8) unpackedNumbers {
	return unpackReplacementNumber(mapEntry(shupaiReplacementNumbers, hash(counts, shupaiHash[:])))
}

func honorNumbers(counts []uint8) unpackedNumbers {
	return unpackReplacementNumber(mapEntry(zipaiReplacementNumbers, hash(counts, zipaiHash[:])))
}

func hash(counts []uint8, table [][15][5]uint32) int {
	h, tiles := 0, 0
	for i, count := range counts {
		tiles += int(count)
		h += int(table[i][tiles][count])
	}

	return h
}

func mapEntry(blob string, index int) uint32 {
	entry := blob[entryBytes*index : entryBytes*index+entryBytes]
	return uint32(entry[0]) | uint32(entry[1])<<8 | uint32(entry[2])<<16 | uint32(entry[3])<<24
}

func unpackReplacementNumber(pack uint32) unpackedNumbers {
	return unpackedNumbers{
		0,
		pack & 0b11,
		(pack >> 2) & 0b111,
		(pack >> 5) & 0b1111,
		(pack >> 9) & 0b1111,
		(pack >> 13) & 0b11,
		(pack >> 15) & 0b111,
		(pack >> 18) & 0b1111,
		(pack >> 22) & 0b1111,
		(pack >> 26) & 0b1111,
	}
}

func updateDP(lhs *unpackedNumbers, rhs unpackedNumbers) {
	updateDPFinal(lhs, rhs)
	for i := pairedOffset - 1; i >= 1; i-- {
		r := min(lhs[i], rhs[i])
		for j := 1; j < i; j++ {
			r = min(r, lhs[j]+rhs[i-j])
		}

		lhs[i] = r
	}
}

func updateDPFinal(lhs *unpackedNumbers, rhs unpackedNumbers) {
	for i := len(lhs) - 1; i >= pairedOffset; i-- {
		r := min(lhs[i], rhs[i])
		for j := pairedOffset; j < i; j++ {
			r = min(r, lhs[j]+rhs[i-j], lhs[i-j]+rhs[j])
		}

		lhs[i] = r
	}
}
