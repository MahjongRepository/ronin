package main

import (
	"fmt"
	"reflect"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	dieFaces      = 6
	diceOutcomes  = dieFaces * dieFaces
	lowestSum     = 2
	highestSum    = 2 * dieFaces
	honorTiles    = (tile.KindCount - int(tile.HonorStart)) * tile.CopiesPerKind
	redFives      = 3
	shantenMax    = 6
	permutations  = 24
	expectedPairs = 3.0
)

func diceSumProbabilities() []float64 {
	probabilities := make([]float64, 0, highestSum-lowestSum+1)
	for total := lowestSum; total <= highestSum; total++ {
		probabilities = append(probabilities, float64(dieFaces-abs(total-dieFaces-1))/diceOutcomes)
	}
	return probabilities
}

func abs(n int) int {
	return max(n, -n)
}

func firstDealerProbabilities() []float64 {
	sums := diceSumProbabilities()
	counts := make([]float64, tile.SeatCount)
	for first := lowestSum; first <= highestSum; first++ {
		for second := lowestSum; second <= highestSum; second++ {
			temporary := (first - 1) % tile.SeatCount
			counts[(temporary+second-1)%tile.SeatCount] += sums[first-lowestSum] * sums[second-lowestSum]
		}
	}
	return counts
}

func seatPermutationIndex(seats [tile.SeatCount]int) int {
	remaining := identity(tile.SeatCount)
	index := 0
	for i, seat := range seats {
		position := slices.Index(remaining, seat)
		index = index*(tile.SeatCount-i) + position
		remaining = slices.Delete(remaining, position, position+1)
	}
	return index
}

func shantenLabels(lowest int) []string {
	var labels []string
	for value := lowest; value <= shantenMax; value++ {
		labels = append(labels, strconv.Itoa(value))
	}
	return labels
}

func seatShantenStats() []*meanStat {
	stats := make([]*meanStat, tile.SeatCount)
	for offset := range stats {
		stats[offset] = newMeanStat("mean shanten of 13-tile hands, seat " + strconv.Itoa(offset) + " after the dealer")
	}
	return stats
}

type gameAccumulator struct {
	adjacent, pairs, honors, reds, shanten13, shanten14, sameID, sameType []int
	seatShanten                                                           [tile.SeatCount][]int
}

type report struct {
	metadata         metadata
	errors           []string
	games            int
	walls            int
	consecutivePairs int
	identicalWalls   int
	families         []familySummary
	means            []meanSummary
	comparisons      []comparison
}

type measurement struct {
	games            int
	walls            int
	consecutivePairs int
	identicalWalls   int
	errors           []string

	tileByPosition   *cellFamily
	typeByPosition   *cellFamily
	dealtTypeBySeat  *cellFamily
	doraType         *cellFamily
	breakFaces       *cellFamily
	breakPairs       *cellFamily
	breakSums        *cellFamily
	dealerFaces      *cellFamily
	firstDealer      *cellFamily
	dealerInputIndex *cellFamily
	seatPermutation  *cellFamily

	adjacentTypes     *meanStat
	handPairs         *meanStat
	handHonors        *meanStat
	handReds          *meanStat
	sameIDNextRound   *meanStat
	sameTypeNextRound *meanStat

	engineShanten13    fractionHistogram
	engineShanten14    fractionHistogram
	controlShanten13   fractionHistogram
	controlShanten14   fractionHistogram
	engineSeatShanten  []*meanStat
	controlSeatShanten []*meanStat
}

func newMeasurement() *measurement {
	const shanten13Name, shanten14Name = "shanten of 13-tile hands", "shanten of the dealer's 14 tiles"
	return &measurement{
		tileByPosition: newCellFamily("tile id by wall position", uniform(tile.TileIDCount), tile.TileIDCount),
		typeByPosition: newCellFamily("tile type by wall position", uniform(tile.KindCount), tile.TileIDCount),
		dealtTypeBySeat: newSampledCellFamily(
			"tile type among the dealt 13, by seat after the dealer",
			uniform(tile.KindCount),
			tile.SeatCount,
			float64(tile.TileIDCount-handSize)/float64(tile.TileIDCount-1),
		),
		doraType:         newCellFamily("first dora indicator type", uniform(tile.KindCount), 1),
		breakFaces:       newCellFamily("wall-break dice faces, by die", uniform(dieFaces), 2),
		breakPairs:       newCellFamily("wall-break dice ordered pairs", uniform(diceOutcomes), 1),
		breakSums:        newCellFamily("wall-break dice sum (triangular)", diceSumProbabilities(), 1),
		dealerFaces:      newCellFamily("first-dealer dice faces, by roll and die", uniform(dieFaces), 4),
		firstDealer:      newCellFamily("first dealer seat (two-roll rule)", firstDealerProbabilities(), 1),
		dealerInputIndex: newCellFamily("first dealer among the input players", uniform(tile.SeatCount), 1),
		seatPermutation:  newCellFamily("seat permutation", uniform(permutations), 1),
		adjacentTypes:    newExpectedMeanStat("adjacent equal types per wall", expectedPairs),
		handPairs: newExpectedMeanStat(
			"equal-type pairs per 13-tile hand",
			float64(handSize*(handSize-1)/2)*(tile.CopiesPerKind-1)/(tile.TileIDCount-1),
		),
		handHonors: newExpectedMeanStat("honors per 13-tile hand", float64(handSize*honorTiles)/tile.TileIDCount),
		handReds:   newExpectedMeanStat("red fives per 13-tile hand", float64(handSize*redFives)/tile.TileIDCount),
		sameIDNextRound: newExpectedMeanStat(
			"positions holding the same tile id in consecutive rounds", 1,
		),
		sameTypeNextRound: newExpectedMeanStat(
			"positions holding the same tile type in consecutive rounds",
			float64(tile.TileIDCount)/tile.KindCount,
		),
		engineShanten13:    newFractionHistogram(shanten13Name, shantenLabels(0)),
		engineShanten14:    newFractionHistogram(shanten14Name, shantenLabels(-1)),
		controlShanten13:   newFractionHistogram(shanten13Name, shantenLabels(0)),
		controlShanten14:   newFractionHistogram(shanten14Name, shantenLabels(-1)),
		engineSeatShanten:  seatShantenStats(),
		controlSeatShanten: seatShantenStats(),
	}
}

func (m *measurement) observeEngine(game gameSample) error {
	m.games++
	m.observeSeating(game)
	var acc gameAccumulator
	for _, sample := range game.rounds {
		err := checkRound(sample)
		if err != nil {
			m.errors = append(m.errors, fmt.Sprintf("seed %s..., %v", game.seed[:16], err))
			continue
		}

		m.walls++
		m.observePositions(sample, &acc)
		err = m.observeHands(sample, &acc)
		if err != nil {
			return err
		}
		m.observeDice(sample)
	}

	m.observeConsecutiveRounds(game, &acc)
	m.fold(&acc)
	return nil
}

func (m *measurement) observeControl(rounds []controlRound) error {
	var bySeat [tile.SeatCount][]int
	var all, shanten14 []int
	for seat := range tile.SeatCount {
		for _, sample := range rounds {
			value, err := controlShanten(sample.hands[seat])
			if err != nil {
				return err
			}
			bySeat[seat] = append(bySeat[seat], value)
		}
		all = append(all, bySeat[seat]...)
	}
	for _, sample := range rounds {
		value, err := controlShanten(sample.dealerHand)
		if err != nil {
			return err
		}
		shanten14 = append(shanten14, value)
	}

	m.controlShanten13.addGame(all, 0)
	m.controlShanten14.addGame(shanten14, 1)
	for seat, stat := range m.controlSeatShanten {
		stat.add(average(bySeat[seat]))
	}
	return nil
}

func controlShanten(ids []int) (int, error) {
	var counts [tile.KindCount]uint8
	for _, id := range ids {
		counts[id/tile.CopiesPerKind]++
	}
	return shantenOf(counts)
}

func shantenOf(counts [tile.KindCount]uint8) (int, error) {
	hand, err := tile.CountsFromArray(counts)
	if err != nil {
		return 0, fmt.Errorf("count a hand: %w", err)
	}
	value, err := engine.Shanten(hand)
	if err != nil {
		return 0, fmt.Errorf("shanten of a hand: %w", err)
	}
	return value, nil
}

func (m *measurement) verifyRegeneration(game gameSample) error {
	again, err := sampleEngineGame(game.seed, len(game.rounds))
	if err != nil {
		return err
	}
	if !reflect.DeepEqual(again, game) {
		m.errors = append(m.errors, fmt.Sprintf("seed %s... regenerated differently", game.seed[:16]))
	}
	return nil
}

func (m *measurement) report(meta metadata) report {
	means := []*meanStat{
		m.adjacentTypes, m.handPairs, m.handHonors, m.handReds, m.sameIDNextRound, m.sameTypeNextRound,
	}
	r := report{
		metadata:         meta,
		errors:           slices.Clone(m.errors),
		games:            m.games,
		walls:            m.walls,
		consecutivePairs: m.consecutivePairs,
		identicalWalls:   m.identicalWalls,
		comparisons:      m.comparisons(),
	}
	for _, family := range m.cellFamilies() {
		r.families = append(r.families, family.summary())
	}
	for _, stat := range means {
		r.means = append(r.means, stat.summary())
	}
	return r
}

func (m *measurement) familyJSON() []familyJSON {
	families := m.cellFamilies()
	out := make([]familyJSON, len(families))
	for i, family := range families {
		out[i] = family.json()
	}
	return out
}

func (m *measurement) cellFamilies() []*cellFamily {
	return []*cellFamily{
		m.tileByPosition, m.typeByPosition, m.dealtTypeBySeat, m.doraType, m.breakFaces, m.breakPairs,
		m.breakSums, m.dealerFaces, m.firstDealer, m.dealerInputIndex, m.seatPermutation,
	}
}

func (m *measurement) comparisons() []comparison {
	var out []comparison
	for _, pair := range [][2]fractionHistogram{
		{m.engineShanten13, m.controlShanten13},
		{m.engineShanten14, m.controlShanten14},
	} {
		engineSummaries, controlSummaries := pair[0].summaries(), pair[1].summaries()
		threshold := warnThreshold(len(engineSummaries))
		for i := range engineSummaries {
			out = append(out, compare(engineSummaries[i], controlSummaries[i], threshold))
		}
	}

	threshold := warnThreshold(tile.SeatCount)
	for seat := range tile.SeatCount {
		out = append(out, compare(m.engineSeatShanten[seat].summary(), m.controlSeatShanten[seat].summary(), threshold))
	}
	return out
}

func (m *measurement) observeSeating(game gameSample) {
	m.seatPermutation.add(0, seatPermutationIndex(game.seats))
	m.seatPermutation.trials++

	m.firstDealer.add(0, game.firstDealer)
	m.firstDealer.trials++
	m.dealerInputIndex.add(0, slices.Index(game.seats[:], game.firstDealer))
	m.dealerInputIndex.trials++

	for row, face := range []int{game.firstRoll.First, game.firstRoll.Second, game.secondRoll.First, game.secondRoll.Second} {
		m.dealerFaces.add(row, face-1)
	}
	m.dealerFaces.trials++
}

func (m *measurement) observePositions(sample roundSample, acc *gameAccumulator) {
	adjacent := 0
	for position, id := range sample.permutation {
		m.tileByPosition.add(position, id)
		m.typeByPosition.add(position, id/tile.CopiesPerKind)
		if position > 0 && sample.permutation[position-1]/tile.CopiesPerKind == id/tile.CopiesPerKind {
			adjacent++
		}
	}
	m.tileByPosition.trials++
	m.typeByPosition.trials++
	acc.adjacent = append(acc.adjacent, adjacent)
}

func (m *measurement) observeHands(sample roundSample, acc *gameAccumulator) error {
	for offset := range tile.SeatCount {
		hand := sample.handAtOffset(offset)
		counts := kindCounts(hand)
		pairs, honors := 0, 0
		for kind, count := range counts {
			m.dealtTypeBySeat.counts[offset][kind] += int(count)
			pairs += int(count) * (int(count) - 1) / 2
			if tile.Kind(kind).IsHonor() {
				honors += int(count)
			}
		}

		value, err := m.shanten(counts, 0)
		if err != nil {
			return err
		}
		acc.pairs = append(acc.pairs, pairs)
		acc.honors = append(acc.honors, honors)
		acc.reds = append(acc.reds, redFiveCount(hand))
		acc.shanten13 = append(acc.shanten13, value)
		acc.seatShanten[offset] = append(acc.seatShanten[offset], value)
	}
	m.dealtTypeBySeat.trials += handSize

	value, err := m.shanten(kindCounts(sample.dealerHand()), -1)
	if err != nil {
		return err
	}
	acc.shanten14 = append(acc.shanten14, value)
	m.doraType.add(0, int(sample.deal.DoraIndicator.Kind()))
	m.doraType.trials++
	return nil
}

func kindCounts(hand []tile.TileID) [tile.KindCount]uint8 {
	var counts [tile.KindCount]uint8
	for _, id := range hand {
		counts[id.Kind()]++
	}
	return counts
}

func redFiveCount(hand []tile.TileID) int {
	reds := 0
	for _, id := range hand {
		if id.Tile(tile.AkaDoraEnabled).IsRed() {
			reds++
		}
	}
	return reds
}

func (m *measurement) observeDice(sample roundSample) {
	first, second := sample.dice.First, sample.dice.Second
	m.breakFaces.add(0, first-1)
	m.breakFaces.add(1, second-1)
	m.breakFaces.trials++

	m.breakPairs.add(0, (first-1)*dieFaces+(second-1))
	m.breakPairs.trials++

	m.breakSums.add(0, first+second-lowestSum)
	m.breakSums.trials++
}

func (m *measurement) observeConsecutiveRounds(game gameSample, acc *gameAccumulator) {
	for i := 1; i < len(game.rounds); i++ {
		earlier, later := game.rounds[i-1].permutation, game.rounds[i].permutation
		m.consecutivePairs++
		sameID, sameType := 0, 0
		for position := range earlier {
			if earlier[position] == later[position] {
				sameID++
			}
			if earlier[position]/tile.CopiesPerKind == later[position]/tile.CopiesPerKind {
				sameType++
			}
		}
		acc.sameID = append(acc.sameID, sameID)
		acc.sameType = append(acc.sameType, sameType)
		if earlier == later {
			m.identicalWalls++
		}
	}
}

func (m *measurement) fold(acc *gameAccumulator) {
	for _, pair := range []struct {
		stat   *meanStat
		values []int
	}{
		{m.adjacentTypes, acc.adjacent},
		{m.handPairs, acc.pairs},
		{m.handHonors, acc.honors},
		{m.handReds, acc.reds},
		{m.sameIDNextRound, acc.sameID},
		{m.sameTypeNextRound, acc.sameType},
	} {
		if len(pair.values) > 0 {
			pair.stat.add(average(pair.values))
		}
	}

	if len(acc.shanten13) == 0 {
		return
	}
	m.engineShanten13.addGame(acc.shanten13, 0)
	m.engineShanten14.addGame(acc.shanten14, 1)
	for seat, stat := range m.engineSeatShanten {
		stat.add(average(acc.seatShanten[seat]))
	}
}

func (m *measurement) shanten(counts [tile.KindCount]uint8, lowest int) (int, error) {
	value, err := shantenOf(counts)
	if err != nil {
		return 0, err
	}
	if value < lowest || value > shantenMax {
		return 0, fmt.Errorf("shanten %d outside [%d, %d]", value, lowest, shantenMax)
	}
	return value, nil
}

func average(values []int) float64 {
	sum := 0
	for _, value := range values {
		sum += value
	}
	return float64(sum) / float64(len(values))
}
