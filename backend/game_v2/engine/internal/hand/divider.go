package hand

import (
	"cmp"
	"iter"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	sevenPairs        = 7
	maxSets           = 4
	maxDecompositions = 4
	maxSuitReadings   = 4
	maxBlocks         = sevenPairs
	blocksPerTile     = 5
)

// SetShape is the shape of a concealed set.
type SetShape uint8

// The set shapes.
const (
	Sequence SetShape = iota
	Triplet
)

// Set is three concealed tiles named by the lowest kind: Kind, Kind+1 and Kind+2 for a sequence,
// three of Kind for a triplet.
type Set struct {
	Shape SetShape
	Kind  tile.Kind
}

// SetsAndPair is a pair and up to four sets: four with 14 concealed tiles, one fewer for each 3
// tiles less.
type SetsAndPair struct {
	pair tile.Kind
	sets [maxSets]Set
	len  int
}

// Pair returns the kind of the pair.
func (h SetsAndPair) Pair() tile.Kind {
	return h.pair
}

// Sets returns the sets sorted by lowest kind, a triplet before a sequence of the same kind, as a
// copy.
func (h SetsAndPair) Sets() []Set {
	return slices.Clone(h.sets[:h.len])
}

func (h SetsAndPair) holds(set Set) bool {
	return slices.Contains(h.sets[:h.len], set)
}

// Decomposition is one reading of the concealed tiles of a winning hand: sets and a pair, or seven
// different pairs. Only Divide makes one; the zero value reads as a lone pair of 1m.
type Decomposition struct {
	sevenPairs bool
	pairs      [sevenPairs]tile.Kind
	hand       SetsAndPair
}

// SetsAndPair returns the sets and pair of d, and false when d is seven pairs.
func (d Decomposition) SetsAndPair() (SetsAndPair, bool) {
	return d.hand, !d.sevenPairs
}

// SevenPairs returns the kinds of the seven pairs in ascending order, and false when d is sets and
// a pair.
func (d Decomposition) SevenPairs() ([sevenPairs]tile.Kind, bool) {
	return d.pairs, d.sevenPairs
}

// KindSets returns every set of d as its kinds, the pair included, sorted by lowest kind and then
// by shape: triplet, pair, sequence. A pair is [k, k], a triplet [k, k, k] and a sequence
// [k, k+1, k+2].
func (d Decomposition) KindSets() [][]tile.Kind {
	blocks := d.blocks()
	sets := make([][]tile.Kind, 0, blocks.len)
	for _, b := range blocks.all() {
		sets = append(sets, b.kinds())
	}
	return sets
}

// WinBlocks yields each distinct concealed block of d holding the winning kind once, in KindSets
// order: the sequences from two and one kinds below, the triplet, the pair, then the sequence from
// the winning kind. Seven pairs yields the pair of the winning kind.
func (d Decomposition) WinBlocks(win tile.Kind) iter.Seq[WinBlock] {
	return func(yield func(WinBlock) bool) {
		for _, b := range d.winBlocks(win) {
			if b.held && !yield(b.block) {
				return
			}
		}
	}
}

type heldWinBlock struct {
	block WinBlock
	held  bool
}

func (d Decomposition) winBlocks(win tile.Kind) [blocksPerTile]heldWinBlock {
	var blocks [blocksPerTile]heldWinBlock
	if d.sevenPairs {
		blocks[0] = heldWinBlock{PairWinBlock(), slices.Contains(d.pairs[:], win)}
		return blocks
	}

	heldSet := func(set Set) heldWinBlock {
		return heldWinBlock{SetWinBlock(set), d.hand.holds(set)}
	}
	if start, ok := checkedSub(win, 2); ok {
		blocks[0] = heldSet(Set{Sequence, start})
	}
	if start, ok := checkedSub(win, 1); ok {
		blocks[1] = heldSet(Set{Sequence, start})
	}
	blocks[2] = heldSet(Set{Triplet, win})
	blocks[3] = heldWinBlock{PairWinBlock(), d.hand.pair == win}
	blocks[4] = heldSet(Set{Sequence, win})
	return blocks
}

func checkedSub(kind, n tile.Kind) (tile.Kind, bool) {
	if kind < n {
		return 0, false
	}
	return kind - n, true
}

// Reading returns d's sets added to the melds' sets.
func (d Decomposition) Reading(melds MeldSets) Reading {
	if d.sevenPairs {
		return Reading{SevenPairs: true}
	}

	reading := Reading{
		Pair:         d.hand.pair,
		Sequences:    melds.sequences,
		Triplets:     melds.triplets,
		OpenTriplets: melds.openTriplets,
		Kans:         melds.kans,
	}
	var unpairedSequences uint64
	for _, set := range d.hand.sets[:d.hand.len] {
		bit := uint64(1) << set.Kind
		switch set.Shape {
		case Sequence:
			if unpairedSequences&bit != 0 {
				reading.IdenticalSequencePairs++
			}
			unpairedSequences ^= bit
			reading.Sequences |= bit
		case Triplet:
			reading.Triplets |= bit
		}
	}
	return reading
}

// WinBlock is the concealed block of a reading that the winning tile completes: a set, or the
// pair, which is also the seven-pairs pair of the winning kind.
type WinBlock struct {
	set   Set
	isSet bool
}

// PairWinBlock returns the win block of the pair.
func PairWinBlock() WinBlock {
	return WinBlock{}
}

// SetWinBlock returns the win block of set.
func SetWinBlock(set Set) WinBlock {
	return WinBlock{set: set, isSet: true}
}

// Set returns the set of b, and false when b is the pair.
func (b WinBlock) Set() (Set, bool) {
	return b.set, b.isSet
}

// MeldSets holds the declared melds' sets as masks of kinds, kind 0 the lowest bit, the same in
// every reading.
type MeldSets struct {
	sequences    uint64
	triplets     uint64
	openTriplets uint64
	kans         uint64
}

// MeldSetsOf marks a chi's first kind as a sequence, and a pon's or any kan's as a triplet, open
// unless it is a closed kan.
func MeldSetsOf(melds []meld.Meld) MeldSets {
	var sets MeldSets
	for _, m := range melds {
		bit := uint64(1) << m.FirstKind()
		switch m.Kind() {
		case meld.Chi:
			sets.sequences |= bit
		case meld.Pon:
			sets.triplets |= bit
			sets.openTriplets |= bit
		case meld.OpenKan:
			sets.triplets |= bit
			sets.openTriplets |= bit
			sets.kans |= bit
		case meld.ClosedKan:
			sets.triplets |= bit
			sets.kans |= bit
		}
	}
	return sets
}

// Reading is one reading's sets with the declared melds' sets, as masks of kinds, kind 0 the
// lowest bit. Sequences holds the first kind of every sequence and Triplets every triplet and
// quad, concealed or declared; OpenTriplets the pons and kans declared open; Kans the declared
// quads, open or closed. IdenticalSequencePairs counts the concealed sequences that repeat an
// unpaired one: 1 is iipeikou, 2 ryanpeikou. A seven-pairs reading sets SevenPairs and leaves
// every other field zero.
type Reading struct {
	SevenPairs             bool
	Pair                   tile.Kind
	Sequences              uint64
	IdenticalSequencePairs int
	Triplets               uint64
	OpenTriplets           uint64
	Kans                   uint64
}

// WrongTileCountError reports a concealed tile count no winning hand has: it holds 2, 5, 8, 11 or
// 14.
type WrongTileCountError struct {
	Count int
}

func (e WrongTileCountError) Error() string {
	return "a winning hand has 2, 5, 8, 11 or 14 concealed tiles, not " + strconv.Itoa(e.Count)
}

// Decompositions holds the readings Divide gives, at most four.
type Decompositions struct {
	readings [maxDecompositions]Decomposition
	len      int
}

// Len returns how many readings there are.
func (ds Decompositions) Len() int {
	return ds.len
}

// All yields the readings in order.
func (ds Decompositions) All() iter.Seq[Decomposition] {
	return func(yield func(Decomposition) bool) {
		for _, d := range ds.readings[:ds.len] {
			if !yield(d) {
				return
			}
		}
	}
}

func (ds *Decompositions) push(d Decomposition) {
	ds.readings[ds.len] = d
	ds.len++
}

// Divide returns every reading of the concealed tiles of a winning hand as sets and one pair, plus
// seven pairs when the 14 tiles are seven different pairs. Pass the tiles outside the declared
// melds, the winning tile included. Four of a kind reads as a triplet and one more tile; quads come
// only from melds. A hand that does not divide, thirteen orphans included, gives no readings.
//
// The readings are sorted, each compared as the list KindSets gives, set by set: by lowest kind,
// then by shape in the order triplet, pair, sequence.
//
// A WrongTileCountError when the tile count is not 2, 5, 8, 11 or 14.
func Divide(concealed tile.Counts) (Decompositions, error) {
	counts := concealed.Array()
	count := total(counts)
	if count > tile.MaxConcealedTiles || count%setTiles != 2 {
		return Decompositions{}, WrongTileCountError{Count: count}
	}

	ds := divideConcealed(counts)
	var keyed [maxDecompositions]keyedDecomposition
	for i, d := range ds.readings[:ds.len] {
		keyed[i] = keyedDecomposition{d, d.blocks()}
	}
	slices.SortStableFunc(keyed[:ds.len], func(a, b keyedDecomposition) int {
		return slices.CompareFunc(a.key.all(), b.key.all(), block.compare)
	})
	for i, k := range keyed[:ds.len] {
		ds.readings[i] = k.decomposition
	}
	return ds, nil
}

type keyedDecomposition struct {
	decomposition Decomposition
	key           blockList
}

type blockShape uint8

const (
	tripletBlock blockShape = iota
	pairBlock
	sequenceBlock
)

type block struct {
	kind  tile.Kind
	shape blockShape
}

func blockOf(set Set) block {
	if set.Shape == Sequence {
		return block{set.Kind, sequenceBlock}
	}
	return block{set.Kind, tripletBlock}
}

func (b block) compare(other block) int {
	if c := cmp.Compare(b.kind, other.kind); c != 0 {
		return c
	}
	return cmp.Compare(b.shape, other.shape)
}

func (b block) kinds() []tile.Kind {
	if b.shape == sequenceBlock {
		return []tile.Kind{b.kind, b.kind + 1, b.kind + 2}
	}
	if b.shape == pairBlock {
		return []tile.Kind{b.kind, b.kind}
	}
	return []tile.Kind{b.kind, b.kind, b.kind}
}

type blockList struct {
	blocks [maxBlocks]block
	len    int
}

func (l *blockList) all() []block {
	return l.blocks[:l.len]
}

func (l *blockList) push(b block) {
	l.blocks[l.len] = b
	l.len++
}

func (d Decomposition) blocks() blockList {
	var list blockList
	if d.sevenPairs {
		for _, kind := range d.pairs {
			list.push(block{kind, pairBlock})
		}
	} else {
		for _, set := range d.hand.sets[:d.hand.len] {
			list.push(blockOf(set))
		}
		list.push(block{d.hand.pair, pairBlock})
	}
	slices.SortFunc(list.all(), block.compare)
	return list
}

type partReading struct {
	pair    tile.Kind
	hasPair bool
	sets    [maxSets]Set
	len     int
}

func (r partReading) with(set Set) partReading {
	r.sets[r.len] = set
	r.len++
	return r
}

type suitReadings struct {
	readings [maxSuitReadings]partReading
	len      int
}

func (rs *suitReadings) push(r partReading) {
	rs.readings[rs.len] = r
	rs.len++
}

func divideConcealed(counts [tile.KindCount]uint8) Decompositions {
	var ds Decompositions
	if pairs, ok := sevenPairsOf(counts); ok {
		ds.push(Decomposition{sevenPairs: true, pairs: pairs})
	}

	suits := suitsOf(counts)
	remainders := suitRemainders(suits)
	honorCounts := counts[tile.HonorStart:]
	if !isOnePairSplit(remainders, honorCounts) {
		return ds
	}
	honors, ok := honorsReading(honorCounts)
	if !ok {
		return ds
	}

	var parts [3]suitReadings
	for i, start := range tile.SuitStarts() {
		parts[i] = suitReadingsOf(suits[i], start, remainders[i])
		if parts[i].len == 0 {
			return ds
		}
	}

	for _, man := range parts[0].readings[:parts[0].len] {
		for _, pin := range parts[1].readings[:parts[1].len] {
			for _, sou := range parts[2].readings[:parts[2].len] {
				ds.push(Decomposition{hand: joinParts([4]partReading{man, pin, sou, honors})})
			}
		}
	}
	return ds
}

func joinParts(parts [4]partReading) SetsAndPair {
	var hand SetsAndPair
	for _, part := range parts {
		if part.hasPair {
			hand.pair = part.pair
		}
		hand.len += copy(hand.sets[hand.len:], part.sets[:part.len])
	}
	slices.SortFunc(hand.sets[:hand.len], func(a, b Set) int {
		return blockOf(a).compare(blockOf(b))
	})
	return hand
}

func sevenPairsOf(counts [tile.KindCount]uint8) ([sevenPairs]tile.Kind, bool) {
	var pairs [sevenPairs]tile.Kind
	found := 0
	for kind, count := range counts {
		switch count {
		case 0:
		case 2:
			if found < sevenPairs {
				pairs[found] = tile.Kind(kind)
			}
			found++
		default:
			return pairs, false
		}
	}
	return pairs, found == sevenPairs
}

func suitReadingsOf(suit suitCounts, start tile.Kind, remainder int) suitReadings {
	var readings suitReadings
	if remainder != 2 {
		collectReadings(suit, partReading{}, 0, start, &readings)
		return readings
	}

	for at := pairOffset(suit); at < kindsPerSuit; at += blockTiles {
		if suit[at] < 2 {
			continue
		}
		rest := suit
		rest[at] -= 2
		pair := partReading{pair: start + tile.Kind(at), hasPair: true}
		collectReadings(rest, pair, 0, start, &readings)
	}
	return readings
}

func collectReadings(
	suit suitCounts, reading partReading, at int, start tile.Kind, readings *suitReadings,
) {
	for at < kindsPerSuit && suit[at] == 0 {
		at++
	}
	if at == kindsPerSuit {
		readings.push(reading)
		return
	}

	kind := start + tile.Kind(at)
	if at < kindsPerSuit-2 && suit[at+1] >= 1 && suit[at+2] >= 1 {
		rest := suit
		rest[at]--
		rest[at+1]--
		rest[at+2]--
		collectReadings(rest, reading.with(Set{Sequence, kind}), at, start, readings)
	}
	if suit[at] == setTiles {
		rest := suit
		rest[at] = 0
		collectReadings(rest, reading.with(Set{Triplet, kind}), at+1, start, readings)
	}
}

func honorsReading(honors []uint8) (partReading, bool) {
	var reading partReading
	for i, count := range honors {
		kind := tile.HonorStart + tile.Kind(i)
		switch count {
		case 0:
		case 2:
			reading.pair, reading.hasPair = kind, true
		case setTiles:
			reading = reading.with(Set{Triplet, kind})
		default:
			return reading, false
		}
	}
	return reading, true
}
