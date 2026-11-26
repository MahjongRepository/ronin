package hand_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/hand"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func TestTenpaiDiscards_WhenDrawnHandIsComplete_ShouldKeepTenpaiOnEveryDiscard(t *testing.T) {
	got := hand.TenpaiDiscards(mustCounts(t, "123456789m11p234s"), tile.Counts{})

	if s := kindsString(t, got); s != "123456789m1p234s" {
		t.Errorf("TenpaiDiscards = %s, want 123456789m1p234s", s)
	}
}

func TestWaits_WhenRegularHandWaitsOnATanki_ShouldBeTenpaiOnIt(t *testing.T) {
	closed := mustCounts(t, "123456789m1p234s")

	if s := kindsString(t, hand.Waits(closed, tile.Counts{})); s != "1p" {
		t.Errorf("Waits = %s, want 1p", s)
	}

	if !hand.IsTenpai(closed, tile.Counts{}) {
		t.Error("IsTenpai = false, want true")
	}
}

func TestWaits_WhenSevenPairsAreTenpai_ShouldWaitOnTheSingle(t *testing.T) {
	if s := kindsString(t, hand.Waits(mustCounts(t, "1199m1199p1199s1z"), tile.Counts{})); s != "1z" {
		t.Errorf("Waits = %s, want 1z", s)
	}
}

func TestWaits_WhenThirteenOrphansHoldNoPair_ShouldWaitOnAllThirteen(t *testing.T) {
	got := hand.Waits(mustCounts(t, "19m19p19s1234567z"), tile.Counts{})
	if s := kindsString(t, got); s != "19m19p19s1234567z" || got.Len() != 13 {
		t.Errorf("Waits = %s (%d), want all 13 terminals and honors", s, got.Len())
	}
}

func TestClosedWaits_WhenAMeldTookThreeTiles_ShouldStillBeTenpai(t *testing.T) {
	closed := mustCounts(t, "123456m1p234s")

	if s := kindsString(t, hand.ClosedWaits(closed)); s != "1p" {
		t.Errorf("ClosedWaits = %s, want 1p", s)
	}

	if !hand.IsTenpai(closed, mustCounts(t, "777z")) {
		t.Error("IsTenpai = false, want true")
	}
}

func TestWaits_WhenHandWaitsOnAnEdge_ShouldBeTenpaiOnThreePin(t *testing.T) {
	closed := mustCounts(t, "123456789m1255p")

	if s := kindsString(t, hand.Waits(closed, tile.Counts{})); s != "3p" {
		t.Errorf("Waits = %s, want 3p", s)
	}

	if !hand.IsTenpai(closed, tile.Counts{}) {
		t.Error("IsTenpai = false, want true")
	}
}

func TestWaits_WhenTheClosedPartAndAPonHoldEveryCopy_ShouldBeKaraten(t *testing.T) {
	closed, pon := mustCounts(t, "123456789m9p"), mustCounts(t, "999p")

	if s := kindsString(t, hand.ClosedWaits(closed)); s != "9p" {
		t.Errorf("ClosedWaits = %s, want 9p", s)
	}

	if got := hand.Waits(closed, pon); !got.IsEmpty() {
		t.Errorf("Waits = %s, want none", kindsString(t, got))
	}

	if hand.IsTenpai(closed, pon) {
		t.Error("IsTenpai = true, want false")
	}
}

func TestWaits_WhenThreeCopiesOfTheTankiAreElsewhere_ShouldBeTenpai(t *testing.T) {
	closed := mustCounts(t, "111234567m555p9s")

	if s := kindsString(t, hand.Waits(closed, tile.Counts{})); s != "9s" {
		t.Errorf("Waits = %s, want 9s", s)
	}

	if !hand.IsTenpai(closed, tile.Counts{}) {
		t.Error("IsTenpai = false, want true")
	}
}

func TestClosedWaits_WhenTheClosedPartHoldsFourOfAKind_ShouldNeverWaitOnIt(t *testing.T) {
	closed := mustCounts(t, "111123m456p5578s")
	fifthOneManWouldComplete := mustCounts(t, "1111234567m888p")

	if s := kindsString(t, hand.ClosedWaits(closed)); s != "69s" {
		t.Errorf("ClosedWaits = %s, want 69s", s)
	}

	if s := kindsString(t, hand.Waits(closed, tile.Counts{})); s != "69s" {
		t.Errorf("Waits = %s, want 69s", s)
	}

	if s := kindsString(t, hand.ClosedWaits(fifthOneManWouldComplete)); s != "47m" {
		t.Errorf("ClosedWaits(1111234567m888p) = %s, want 47m", s)
	}
}

func TestIsTenpai_WhenAClosedKanHoldsEveryCopyOfTheOnlyWait_ShouldBeFalse(t *testing.T) {
	fiveManKan := mustCounts(t, "5555m")

	if hand.IsTenpai(mustCounts(t, "46m234567p77s"), fiveManKan) {
		t.Error("IsTenpai = true, want false")
	}

	if got := hand.TenpaiDiscards(mustCounts(t, "46m234567p77s1z"), fiveManKan); !got.IsEmpty() {
		t.Errorf("TenpaiDiscards = %s, want none", kindsString(t, got))
	}
}

func TestTenpaiDiscards_WhenHandHasAClosedKan_ShouldKeepOnlyTheWaitsKeepingDiscards(t *testing.T) {
	oneManKan := mustCounts(t, "1111m")

	if s := kindsString(t, hand.TenpaiDiscards(mustCounts(t, "2345678889m1z"), oneManKan)); s != "9m1z" {
		t.Errorf("TenpaiDiscards = %s, want 9m1z", s)
	}

	if s := kindsString(t, hand.Waits(mustCounts(t, "2345678889m"), oneManKan)); s != "479m" {
		t.Errorf("Waits = %s, want 479m", s)
	}
}

func TestTenpaiDiscards_WhenDrawnHandIsCompleteInOneSuit_ShouldOfferEveryDiscard(t *testing.T) {
	if s := kindsString(t, hand.TenpaiDiscards(mustCounts(t, "11234567888999m"), tile.Counts{})); s != "123456789m" {
		t.Errorf("TenpaiDiscards = %s, want 123456789m", s)
	}
}

func TestTenpaiDiscards_WhenDrawnHandHoldsFourOfAKind_ShouldKeepTheDiscardsThatLeaveWaits(t *testing.T) {
	if s := kindsString(t, hand.TenpaiDiscards(mustCounts(t, "1111234567m888p9s"), tile.Counts{})); s != "147m9s" {
		t.Errorf("TenpaiDiscards = %s, want 147m9s", s)
	}

	if s := kindsString(t, hand.ClosedWaits(mustCounts(t, "111123456m888p9s"))); s != "9s" {
		t.Errorf("ClosedWaits = %s, want 9s", s)
	}
}

func countTotal(counts [tile.KindCount]uint8) int {
	sum := 0
	for _, count := range counts {
		sum += int(count)
	}

	return sum
}

func referenceIsMelds(counts [tile.KindCount]uint8, from int) bool {
	for from < tile.KindCount && counts[from] == 0 {
		from++
	}

	if from == tile.KindCount {
		return true
	}

	if counts[from] >= 3 {
		rest := counts
		rest[from] -= 3
		if referenceIsMelds(rest, from) {
			return true
		}
	}

	isSequenceStart := from < int(tile.HonorStart) && from%9 <= 6
	if isSequenceStart && counts[from+1] > 0 && counts[from+2] > 0 {
		rest := counts
		rest[from]--
		rest[from+1]--
		rest[from+2]--
		return referenceIsMelds(rest, from)
	}

	return false
}

func referenceIsAgari(counts [tile.KindCount]uint8) bool {
	if countTotal(counts) > tile.MaxConcealedTiles {
		return false
	}

	pairs, orphans, orphanPair := 0, 0, false
	for kind, count := range counts {
		if count == 2 {
			pairs++
		}

		if tile.Kind(kind).IsTerminalOrHonor() && count > 0 {
			orphans++
			orphanPair = orphanPair || count == 2
		}
	}

	if pairs == 7 && countTotal(counts) == 14 {
		return true
	}

	if orphans == 13 && orphanPair && countTotal(counts) == 14 {
		return true
	}

	for kind, count := range counts {
		if count < 2 {
			continue
		}

		rest := counts
		rest[kind] -= 2
		if referenceIsMelds(rest, 0) {
			return true
		}
	}

	return false
}

func referenceClosedWaits(counts [tile.KindCount]uint8) []tile.Kind {
	if countTotal(counts)%3 != 1 {
		return nil
	}

	var waits []tile.Kind
	for kind := range tile.Kind(tile.KindCount) {
		if counts[kind] >= tile.CopiesPerKind {
			continue
		}

		completed := counts
		completed[kind]++
		if referenceIsAgari(completed) {
			waits = append(waits, kind)
		}
	}

	return waits
}

func referenceWaits(closed, melded [tile.KindCount]uint8) []tile.Kind {
	var waits []tile.Kind
	for _, kind := range referenceClosedWaits(closed) {
		if closed[kind]+melded[kind] < tile.CopiesPerKind {
			waits = append(waits, kind)
		}
	}

	return waits
}

func referenceTenpaiDiscards(closed, melded [tile.KindCount]uint8) []tile.Kind {
	if countTotal(closed)%3 != 2 {
		return nil
	}

	var discards []tile.Kind
	for kind := range tile.Kind(tile.KindCount) {
		if closed[kind] == 0 {
			continue
		}

		rest := closed
		rest[kind]--
		if len(referenceWaits(rest, melded)) > 0 {
			discards = append(discards, kind)
		}
	}

	return discards
}

func lowestShanten(t *testing.T, closed tile.Counts) int {
	t.Helper()
	lowest, err := shanten.Lowest(closed)
	if err != nil {
		t.Fatalf("Lowest(%v) error = %v", closed.Array(), err)
	}

	return lowest
}

func checkWaitsMatchReference(t *testing.T, closed, melded tile.Counts) []tile.Kind {
	t.Helper()
	wantClosed := referenceClosedWaits(closed.Array())
	want := referenceWaits(closed.Array(), melded.Array())
	gotClosed := slices.Collect(hand.ClosedWaits(closed).All())
	got := slices.Collect(hand.Waits(closed, melded).All())

	if !slices.Equal(gotClosed, wantClosed) {
		t.Errorf("ClosedWaits(%v) = %v, want %v", closed.Array(), gotClosed, wantClosed)
	}

	if !slices.Equal(got, want) {
		t.Errorf("Waits(%v, %v) = %v, want %v", closed.Array(), melded.Array(), got, want)
	}

	if tenpai := hand.IsTenpai(closed, melded); tenpai != (len(want) > 0) {
		t.Errorf("IsTenpai(%v, %v) = %v, want %v", closed.Array(), melded.Array(), tenpai, len(want) > 0)
	}

	return got
}

func checkDiscardsMatchReference(t *testing.T, closed, melded tile.Counts) []tile.Kind {
	t.Helper()
	want := referenceTenpaiDiscards(closed.Array(), melded.Array())
	got := slices.Collect(hand.TenpaiDiscards(closed, melded).All())
	if !slices.Equal(got, want) {
		t.Errorf("TenpaiDiscards(%v, %v) = %v, want %v", closed.Array(), melded.Array(), got, want)
	}

	return got
}

func TestTenpaiDiscards_WhenHandIsFixed_ShouldMatchTheReference(t *testing.T) {
	tests := []struct {
		name, closed, melded string
		shanten              int
		discards             string
	}{
		{name: "tenpai", closed: "123456789m1255p9s", melded: "", shanten: 0, discards: "9s"},
		{name: "one shanten", closed: "123456789m1358p9s", melded: "", shanten: 1, discards: ""},
		{name: "two shanten", closed: "123456789m159p1s5z", melded: "", shanten: 2, discards: ""},
		{name: "complete", closed: "11234567888999m", melded: "", shanten: -1, discards: "123456789m"},
		{name: "tanki behind a pon left on one discard", closed: "123456789m9p1z", melded: "999p", shanten: 0, discards: "9p"},
		{name: "karaten behind a closed kan", closed: "46m234567p77s1z", melded: "5555m", shanten: 0, discards: ""},
		{name: "closed kan of one man", closed: "2345678889m1z", melded: "1111m", shanten: 0, discards: "9m1z"},
		{name: "four copies in the closed part", closed: "1111234567m888p9s", melded: "", shanten: 0, discards: "147m9s"},
		{name: "four copies one shanten", closed: "1111m234p567s13s57z", melded: "", shanten: 1, discards: ""},
		{name: "chiitoitsu tenpai", closed: "1199m1199p1199s12z", melded: "", shanten: 0, discards: "12z"},
		{name: "chiitoitsu one shanten", closed: "1199m1199p11s1234z", melded: "", shanten: 1, discards: ""},
		{name: "kokushi tenpai", closed: "19m19p19s1234567z5m", melded: "", shanten: 0, discards: "5m"},
		{name: "kokushi one shanten", closed: "19m19p19s123456z55m", melded: "", shanten: 1, discards: ""},
		{name: "eleven tiles tenpai", closed: "123456789m1p5z", melded: "777z", shanten: 0, discards: "1p5z"},
		{name: "eleven tiles one shanten", closed: "123456m1358p9s", melded: "777z", shanten: 1, discards: ""},
		{name: "eight tiles tenpai", closed: "123m456p7s5z", melded: "111z222z", shanten: 0, discards: "7s5z"},
		{name: "eight tiles one shanten", closed: "123m46p8s9s5z", melded: "111z222z", shanten: 1, discards: ""},
		{name: "eight tiles two shanten", closed: "13m55p9p1s47z", melded: "111z222z", shanten: 2, discards: ""},
		{name: "five tiles complete", closed: "123m55z", melded: "111z222z333z", shanten: -1, discards: "123m5z"},
		{name: "five tiles one shanten", closed: "13m5p9s1z", melded: "111z222z333z", shanten: 1, discards: ""},
		{name: "two tiles karaten on one discard", closed: "1m5z", melded: "555z123p456p789s", shanten: 0, discards: "5z"},
		{name: "two tiles tanki", closed: "1m9p", melded: "123p456p789s777z", shanten: 0, discards: "1m9p"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			closed, melded := mustCounts(t, tc.closed), mustCounts(t, tc.melded)

			if got := lowestShanten(t, closed); got != tc.shanten {
				t.Errorf("Lowest = %d, want %d", got, tc.shanten)
			}

			if got := kindListString(t, checkDiscardsMatchReference(t, closed, melded)); got != tc.discards {
				t.Errorf("TenpaiDiscards = %s, want %s", got, tc.discards)
			}
		})
	}
}

func TestWaits_WhenHandIsFixed_ShouldMatchTheReference(t *testing.T) {
	tests := []struct {
		name, closed, melded    string
		shanten                 int
		closedWaits, waitsKinds string
	}{
		{name: "tenpai", closed: "123456789m1255p", melded: "", shanten: 0, closedWaits: "3p", waitsKinds: "3p"},
		{name: "one shanten", closed: "123456789m1358p", melded: "", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "two shanten", closed: "123456789m159p1s", melded: "", shanten: 2, closedWaits: "", waitsKinds: ""},
		{name: "chiitoitsu tenpai", closed: "1199m1199p1199s1z", melded: "", shanten: 0, closedWaits: "1z", waitsKinds: "1z"},
		{name: "chiitoitsu one shanten", closed: "1199m1199p11s123z", melded: "", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "kokushi thirteen-sided", closed: "19m19p19s1234567z", melded: "", shanten: 0, closedWaits: "19m19p19s1234567z", waitsKinds: "19m19p19s1234567z"},
		{name: "kokushi single wait", closed: "119m19p19s123456z", melded: "", shanten: 0, closedWaits: "7z", waitsKinds: "7z"},
		{name: "kokushi one shanten", closed: "19m19p19s123456z5m", melded: "", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "four copies held", closed: "111123m456p5578s", melded: "", shanten: 0, closedWaits: "69s", waitsKinds: "69s"},
		{name: "fifth copy would complete", closed: "1111234567m888p", melded: "", shanten: 0, closedWaits: "47m", waitsKinds: "47m"},
		{name: "honor quad tanki", closed: "123m456p789s1111z", melded: "", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "ten tiles tenpai", closed: "123456m1p234s", melded: "777z", shanten: 0, closedWaits: "1p", waitsKinds: "1p"},
		{name: "ten tiles one shanten", closed: "123456m1358p", melded: "777z", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "karaten behind a pon", closed: "123456789m9p", melded: "999p", shanten: 0, closedWaits: "9p", waitsKinds: ""},
		{name: "karaten behind a closed kan", closed: "46m234567p77s", melded: "5555m", shanten: 0, closedWaits: "5m", waitsKinds: ""},
		{name: "seven tiles tenpai", closed: "123m456p7s", melded: "111z222z", shanten: 0, closedWaits: "7s", waitsKinds: "7s"},
		{name: "seven tiles one shanten", closed: "123m46p89s", melded: "111z222z", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "seven tiles two shanten", closed: "13m5p9p1s44z", melded: "111z222z", shanten: 2, closedWaits: "", waitsKinds: ""},
		{name: "four tiles tenpai", closed: "1235m", melded: "111z222z333z", shanten: 0, closedWaits: "5m", waitsKinds: "5m"},
		{name: "four tiles one shanten", closed: "13m5p9s", melded: "111z222z333z", shanten: 1, closedWaits: "", waitsKinds: ""},
		{name: "one tile tanki", closed: "5z", melded: "123p456p789s777z", shanten: 0, closedWaits: "5z", waitsKinds: "5z"},
		{name: "one tile karaten", closed: "5z", melded: "555z123p456p789s", shanten: 0, closedWaits: "5z", waitsKinds: ""},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			closed, melded := mustCounts(t, tc.closed), mustCounts(t, tc.melded)

			if got := lowestShanten(t, closed); got != tc.shanten {
				t.Errorf("Lowest = %d, want %d", got, tc.shanten)
			}

			checkWaitsMatchReference(t, closed, melded)
			if got := kindsString(t, hand.ClosedWaits(closed)); got != tc.closedWaits {
				t.Errorf("ClosedWaits = %s, want %s", got, tc.closedWaits)
			}

			if got := kindsString(t, hand.Waits(closed, melded)); got != tc.waitsKinds {
				t.Errorf("Waits = %s, want %s", got, tc.waitsKinds)
			}
		})
	}
}

type splitMix64 struct {
	state uint64
}

func (r *splitMix64) next() uint64 {
	r.state += 0x9E3779B97F4A7C15
	z := r.state
	z = (z ^ z>>30) * 0xBF58476D1CE4E5B9
	z = (z ^ z>>27) * 0x94D049BB133111EB
	return z ^ z>>31
}

func (r *splitMix64) below(bound int) int {
	return int(r.next() % uint64(bound))
}

type generatedHand struct {
	closed, melded [tile.KindCount]uint8
}

func (h *generatedHand) held(kind int) uint8 {
	return h.closed[kind] + h.melded[kind]
}

func (h *generatedHand) heldAll() [tile.KindCount]uint8 {
	var held [tile.KindCount]uint8
	for kind := range held {
		held[kind] = h.held(kind)
	}

	return held
}

func tryAdd(part *[tile.KindCount]uint8, held [tile.KindCount]uint8, kinds []int) bool {
	var needed [tile.KindCount]uint8
	for _, kind := range kinds {
		needed[kind]++
	}

	for _, kind := range kinds {
		if held[kind]+needed[kind] > tile.CopiesPerKind {
			return false
		}
	}

	for _, kind := range kinds {
		part[kind]++
	}

	return true
}

func randomSet(rng *splitMix64) []int {
	kind := rng.below(tile.KindCount)
	if kind < int(tile.HonorStart) && rng.below(3) > 0 {
		start := kind - kind%9 + min(kind%9, 6)
		return []int{start, start + 1, start + 2}
	}

	return []int{kind, kind, kind}
}

func (h *generatedHand) addGroup(rng *splitMix64, toMelds bool) {
	for {
		group := randomSet(rng)
		if toMelds && group[0] == group[1] && rng.below(4) == 0 {
			group = append(group, group[0])
		}

		held := h.heldAll()
		part := &h.closed
		if toMelds {
			part = &h.melded
		}

		if tryAdd(part, held, group) {
			return
		}
	}
}

func (h *generatedHand) addClosedPair(rng *splitMix64) {
	for {
		kind := rng.below(tile.KindCount)
		if tryAdd(&h.closed, h.heldAll(), []int{kind, kind}) {
			return
		}
	}
}

func (h *generatedHand) removeClosedTile(rng *splitMix64) {
	pick := rng.below(countTotal(h.closed))
	for kind, count := range h.closed {
		if pick < int(count) {
			h.closed[kind]--
			return
		}

		pick -= int(count)
	}
}

func (h *generatedHand) replaceClosedTile(rng *splitMix64) {
	h.removeClosedTile(rng)
	for {
		kind := rng.below(tile.KindCount)
		if h.held(kind) < tile.CopiesPerKind {
			h.closed[kind]++
			return
		}
	}
}

func generateHand(rng *splitMix64) generatedHand {
	var h generatedHand
	melds := [8]int{0, 0, 0, 1, 1, 2, 3, 4}[rng.below(8)]
	shape := 9
	if melds == 0 {
		shape = rng.below(10)
	}

	terminalsAndHonors := tile.TerminalAndHonorKinds()
	switch shape {
	case 0:
		for _, kind := range terminalsAndHonors {
			h.closed[kind] = 1
		}

		h.closed[terminalsAndHonors[rng.below(len(terminalsAndHonors))]]++
	case 1:
		for pairs := 0; pairs < 7; {
			kind := rng.below(tile.KindCount)
			if h.closed[kind] == 0 {
				h.closed[kind] = 2
				pairs++
			}
		}
	default:
		for range melds {
			h.addGroup(rng, true)
		}

		for range 4 - melds {
			h.addGroup(rng, false)
		}

		h.addClosedPair(rng)
	}

	for range rng.below(4) {
		h.replaceClosedTile(rng)
	}

	return h
}

const handsGenerated = 4000

func generateHands(seed uint64, dropATile bool) []generatedHand {
	rng := splitMix64{seed}
	hands := make([]generatedHand, 0, handsGenerated)
	for range handsGenerated {
		h := generateHand(&rng)
		if dropATile {
			h.removeClosedTile(&rng)
		}

		hands = append(hands, h)
	}

	return hands
}

func TestTenpaiDiscards_WhenHandsAreGenerated_ShouldMatchTheReference(t *testing.T) {
	t.Parallel()
	withTenpaiDiscard, guardedOut, openWithTenpaiDiscard := 0, 0, 0
	for _, h := range generateHands(0x5EED0E6E00000001, false) {
		closed, melded := mustCountsFromArray(t, h.closed), mustCountsFromArray(t, h.melded)
		if found := checkDiscardsMatchReference(t, closed, melded); len(found) > 0 {
			withTenpaiDiscard++
			if countTotal(h.closed) < tile.MaxConcealedTiles {
				openWithTenpaiDiscard++
			}
		}

		if lowestShanten(t, closed) >= 1 {
			guardedOut++
		}
	}

	if withTenpaiDiscard < 1500 || guardedOut < 800 || openWithTenpaiDiscard < 1000 {
		t.Errorf("hands with a tenpai discard %d (want 1500+), 1-shanten or worse %d (800+), open with a tenpai discard %d (1000+)",
			withTenpaiDiscard, guardedOut, openWithTenpaiDiscard)
	}
}

func TestWaits_WhenHandsAreGenerated_ShouldMatchTheReference(t *testing.T) {
	t.Parallel()
	tenpai, guardedOut, openTenpai, karaten := 0, 0, 0, 0
	for _, h := range generateHands(0x5EED0E6E00000002, true) {
		closed, melded := mustCountsFromArray(t, h.closed), mustCountsFromArray(t, h.melded)
		found := checkWaitsMatchReference(t, closed, melded)
		if len(found) > 0 {
			tenpai++
			if countTotal(h.closed) < 13 {
				openTenpai++
			}
		}

		if len(found) < hand.ClosedWaits(closed).Len() {
			karaten++
		}

		if lowestShanten(t, closed) >= 1 {
			guardedOut++
		}
	}

	if tenpai < 1300 || guardedOut < 1800 || openTenpai < 900 || karaten < 5 {
		t.Errorf("tenpai %d (want 1300+), 1-shanten or worse %d (1800+), open tenpai %d (900+), karaten %d (5+)",
			tenpai, guardedOut, openTenpai, karaten)
	}
}
