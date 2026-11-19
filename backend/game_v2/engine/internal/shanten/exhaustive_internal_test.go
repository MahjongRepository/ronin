//go:build exhaustive

package shanten

import (
	"fmt"
	"runtime"
	"slices"
	"sync"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	unreachableCost  = 1 << 20
	maxSets          = fullHandSets
	honorKinds       = tile.KindCount - int(tile.HonorStart)
	lastSequenceRank = 6
)

type groupCosts [2][maxSets + 1]int

type groupState [maxSets + 1][2][tile.CopiesPerKind + 1][tile.CopiesPerKind + 1]int

func unreachableState() groupState {
	var state groupState
	for sets := range state {
		for pair := range state[sets] {
			for startedBefore := range state[sets][pair] {
				for startedTwoBefore := range state[sets][pair][startedBefore] {
					state[sets][pair][startedBefore][startedTwoBefore] = unreachableCost
				}
			}
		}
	}
	return state
}

func stepGroup(state groupState, count uint8, sequencesStart bool) groupState {
	next := unreachableState()
	for sets := range state {
		for pair := range state[sets] {
			for before := range state[sets][pair] {
				for twoBefore := range state[sets][pair][before] {
					cost := state[sets][pair][before][twoBefore]
					if cost >= unreachableCost {
						continue
					}
					maxStarted := 0
					if sequencesStart {
						maxStarted = tile.CopiesPerKind - before - twoBefore
					}
					for started := 0; started <= maxStarted; started++ {
						for triplet := range 2 {
							for newPair := range 2 - pair {
								target := tilesPerSet*triplet + 2*newPair + started + before + twoBefore
								nextSets := sets + triplet + started
								if target > tile.CopiesPerKind || nextSets > maxSets {
									continue
								}
								nextCost := cost + max(0, target-int(count))
								slot := &next[nextSets][pair+newPair][started][before]
								*slot = min(*slot, nextCost)
							}
						}
					}
				}
			}
		}
	}
	return next
}

func costsOf(state groupState) groupCosts {
	var costs groupCosts
	for pair := range costs {
		for sets := range costs[pair] {
			costs[pair][sets] = state[sets][pair][0][0]
		}
	}
	return costs
}

func base5(counts []uint8) int {
	index := 0
	for _, count := range slices.Backward(counts) {
		index = index*(tile.CopiesPerKind+1) + int(count)
	}
	return index
}

func countGroups(kinds int, sequences bool) []groupCosts {
	size := 1
	for range kinds {
		size *= tile.CopiesPerKind + 1
	}
	costs := make([]groupCosts, size)
	counts := make([]uint8, kinds)
	var fill func(kind, tiles int, state groupState)
	fill = func(kind, tiles int, state groupState) {
		if kind == kinds {
			costs[base5(counts)] = costsOf(state)
			return
		}
		for count := 0; count <= tile.CopiesPerKind && tiles+count <= tile.MaxConcealedTiles; count++ {
			counts[kind] = uint8(count)
			fill(kind+1, tiles+count, stepGroup(state, uint8(count), sequences && kind <= lastSequenceRank))
		}
		counts[kind] = 0
	}
	start := unreachableState()
	start[0][0][0][0] = 0
	fill(0, 0, start)
	return costs
}

func combine(lhs, rhs groupCosts) groupCosts {
	var combined groupCosts
	for pair := range combined {
		for sets := range combined[pair] {
			best := unreachableCost
			for lhsPair := 0; lhsPair <= pair; lhsPair++ {
				for lhsSets := 0; lhsSets <= sets; lhsSets++ {
					best = min(best, lhs[lhsPair][lhsSets]+rhs[pair-lhsPair][sets-lhsSets])
				}
			}
			combined[pair][sets] = best
		}
	}
	return combined
}

func sevenPairsReplacements(counts [tile.KindCount]uint8) int {
	pairs, singles := 0, 0
	for _, count := range counts {
		switch {
		case count >= 2:
			pairs++
		case count == 1:
			singles++
		}
	}
	pairs = min(pairs, sevenPairs)
	return 2*sevenPairs - 2*pairs - min(singles, sevenPairs-pairs)
}

func thirteenOrphansReplacements(counts [tile.KindCount]uint8) int {
	held, doubled := 0, 0
	for _, kind := range tile.TerminalAndHonorKinds() {
		if counts[kind] >= 1 {
			held++
		}
		if counts[kind] >= 2 {
			doubled = 1
		}
	}
	return kokushiKinds + 1 - held - doubled
}

type independentCount struct {
	suits  []groupCosts
	honors []groupCosts
}

func (c independentCount) lowest(counts [tile.KindCount]uint8, tiles int) int {
	sets := tiles / tilesPerSet
	all := combine(combine(c.suits[base5(counts[0:9])], c.suits[base5(counts[9:18])]), c.suits[base5(counts[18:27])])
	replacements := combine(all, c.honors[base5(counts[27:34])])[1][sets]
	if sets >= fullHandSets {
		replacements = min(replacements, sevenPairsReplacements(counts), thirteenOrphansReplacements(counts))
	}
	return replacements - 1
}

func handTable(tiles int) [tile.KindCount + 1][]uint64 {
	var table [tile.KindCount + 1][]uint64
	for i := range table {
		table[i] = make([]uint64, tiles+1)
	}
	table[tile.KindCount][tiles] = 1
	for i := tile.KindCount - 1; i >= 0; i-- {
		for n := 0; n <= min(tile.CopiesPerKind*i, tiles); n++ {
			for c := 0; c <= min(tiles-n, tile.CopiesPerKind); c++ {
				table[i][n] += table[i+1][n+c]
			}
		}
	}
	return table
}

func decodeHand(index uint64, table [tile.KindCount + 1][]uint64) [tile.KindCount]uint8 {
	var counts [tile.KindCount]uint8
	h, n := uint64(0), 0
	for i := range tile.KindCount {
		for c := range tile.CopiesPerKind + 1 {
			next := table[i+1][n]
			if h+next <= index {
				h += next
				n++
				continue
			}
			counts[i] = uint8(c)
			break
		}
	}
	return counts
}

func TestDecodeHand_WhenIndexIsFirstOrLast_ShouldGiveTheExtremeHands(t *testing.T) {
	for tiles := 1; tiles <= tile.MaxConcealedTiles; tiles++ {
		table := handTable(tiles)
		var firstKinds, lastKinds [tile.KindCount]uint8
		for i := range tiles {
			firstKinds[i/tile.CopiesPerKind]++
			lastKinds[tile.KindCount-1-i/tile.CopiesPerKind]++
		}
		if got := decodeHand(table[0][0]-1, table); got != firstKinds {
			t.Errorf("%d tiles: last index decodes to %v, want %v", tiles, got, firstKinds)
		}
		if got := decodeHand(0, table); got != lastKinds {
			t.Errorf("%d tiles: index 0 decodes to %v, want %v", tiles, got, lastKinds)
		}
	}
}

func TestMaps_WhenEveryGroupIsCountedIndependently_ShouldHoldItsReplacementNumbers(t *testing.T) {
	tests := []struct {
		name      string
		kinds     int
		sequences bool
		table     [][15][5]uint32
		blob      string
	}{
		{"shupai", 9, true, shupaiHash[:], shupaiReplacementNumbers},
		{"zipai", honorKinds, false, zipaiHash[:], zipaiReplacementNumbers},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			costs := countGroups(tc.kinds, tc.sequences)
			groupCountsUpTo14Tiles(tc.kinds, func(counts []uint8) {
				numbers := unpackReplacementNumber(mapEntry(tc.blob, hash(counts, tc.table)))
				want := costs[base5(counts)]
				for pair := range want {
					for sets := range want[pair] {
						if got := int(numbers[pairedOffset*pair+sets]); got != want[pair][sets] {
							t.Fatalf("%v with %d pairs and %d sets: map holds %d, want %d", counts, pair, sets, got, want[pair][sets])
						}
					}
				}
			})
		})
	}
}

func TestLowest_WhenEveryHandOfASizeIsCounted_ShouldMatchAnIndependentCount(t *testing.T) {
	count := independentCount{suits: countGroups(9, true), honors: countGroups(honorKinds, false)}
	for tiles := 1; tiles <= tile.MaxConcealedTiles; tiles++ {
		if tiles%tilesPerSet == 0 {
			continue
		}
		t.Run(fmt.Sprintf("size_%02d", tiles), func(t *testing.T) {
			table := handTable(tiles)
			hands := table[0][0]
			workers := uint64(runtime.GOMAXPROCS(0))
			mismatches := make([]string, workers)
			var wg sync.WaitGroup
			for worker := range workers {
				wg.Go(func() {
					for index := hands * worker / workers; index < hands*(worker+1)/workers; index++ {
						counts := decodeHand(index, table)
						valid, err := tile.CountsFromArray(counts)
						if err != nil {
							mismatches[worker] = fmt.Sprintf("hand %d %v: %v", index, counts, err)
							return
						}
						got, err := Lowest(valid)
						if want := count.lowest(counts, tiles); err != nil || got != want {
							mismatches[worker] = fmt.Sprintf("Lowest(%v) = %d, %v, want %d", counts, got, err, want)
							return
						}
					}
				})
			}
			wg.Wait()
			for _, mismatch := range mismatches {
				if mismatch != "" {
					t.Error(mismatch)
				}
			}
		})
	}
}
