package rng

import (
	"crypto/sha3"
	"math"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type scriptedWords struct {
	t     *testing.T
	words []uint64
}

func script(t *testing.T, words ...uint64) *scriptedWords {
	t.Helper()
	return &scriptedWords{t: t, words: words}
}

func (s *scriptedWords) next() uint64 {
	if len(s.words) == 0 {
		s.t.Fatal("the script has no word left")
	}
	word := s.words[0]
	s.words = s.words[1:]
	return word
}

func littleEndianWords(digest []byte) []uint64 {
	words := make([]uint64, 0, len(digest)/wordBytes)
	for start := 0; start+wordBytes <= len(digest); start += wordBytes {
		var word uint64
		for i := wordBytes - 1; i >= 0; i-- {
			word = word<<8 | uint64(digest[start+i])
		}
		words = append(words, word)
	}
	return words
}

func TestWordStream_ShouldReadLittleEndianShake256OfDomainAndData(t *testing.T) {
	stream := newWordStream("domain:", []byte("da"), []byte("ta"))
	want := littleEndianWords(sha3.SumSHAKE256([]byte("domain:data"), wordBytes*500))
	for i, w := range want {
		if got := stream.next(); got != w {
			t.Fatalf("word %d = %#x, want %#x", i, got, w)
		}
	}
}

func TestWordStream_WhenDomainsDiffer_ShouldYieldDifferentWords(t *testing.T) {
	a := newWordStream("a:", []byte("data")).next()
	b := newWordStream("b:", []byte("data")).next()
	if a == b {
		t.Errorf("both domains read %#x", a)
	}
}

func TestBounded_WhenWordIsInTheIncompleteTopBucket_ShouldRejectItAndReadTheNext(t *testing.T) {
	const lowestRejectedForSix uint64 = math.MaxUint64 - 3
	words := script(t, lowestRejectedForSix, math.MaxUint64, lowestRejectedForSix-1)

	if got, want := bounded(words.next, 6), (lowestRejectedForSix-1)%6; got != want {
		t.Errorf("bounded = %d, want %d", got, want)
	}
	if len(words.words) != 0 {
		t.Errorf("%d words left unread", len(words.words))
	}
}

func TestBounded_WhenBoundIsAPowerOfTwo_ShouldAcceptTheTopWord(t *testing.T) {
	for shift := range 64 {
		bound := uint64(1) << shift
		words := script(t, math.MaxUint64)
		if got := bounded(words.next, bound); got != bound-1 {
			t.Errorf("bounded(MaxUint64, 2^%d) = %d, want %d", shift, got, bound-1)
		}
	}
}

func TestShuffle_WhenEveryChoiceSequenceIsTried_ShouldHitEachPermutationOnce(t *testing.T) {
	seen := map[[3]int]bool{}
	for j := range uint64(3) {
		for k := range uint64(2) {
			items := [3]int{0, 1, 2}
			shuffle(items[:], script(t, j, k).next)
			seen[items] = true
		}
	}
	if len(seen) != 6 {
		t.Errorf("%d distinct permutations, want 6", len(seen))
	}
}

func TestShuffle_WhenFedAStream_ShouldPermuteAllTiles(t *testing.T) {
	tiles := tile.AllTileIDs()
	shuffle(tiles[:], newWordStream("t:", []byte("x")).next)

	var seen [tile.TileIDCount]bool
	for _, id := range tiles {
		seen[id.Index()] = true
	}
	for n, ok := range seen {
		if !ok {
			t.Errorf("tile %d is missing", n)
		}
	}
	if tiles == tile.AllTileIDs() {
		t.Error("the shuffle left every tile in place")
	}
}

func TestRollDice_ShouldMapEachWordToADieFace(t *testing.T) {
	cases := []struct {
		words []uint64
		want  tile.Dice
	}{
		{[]uint64{0, 5}, tile.Dice{First: 1, Second: 6}},
		{[]uint64{7, 11}, tile.Dice{First: 2, Second: 6}},
	}
	for _, c := range cases {
		if got := rollDice(script(t, c.words...).next); got != c.want {
			t.Errorf("rollDice(%v) = %v, want %v", c.words, got, c.want)
		}
	}
}
