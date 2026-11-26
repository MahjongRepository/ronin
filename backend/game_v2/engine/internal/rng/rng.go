package rng

import (
	"crypto/sha3"
	"fmt"
	"math"
	"math/bits"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const Version = "shake256-v1"

const SeedBytes = 96

const (
	wallDomain   = "ronin-wall-shake256-v1:"
	dealerDomain = "ronin-dealer-shake256-v1:"
	seatDomain   = "ronin-seat-shake256-v1:"
	dieFaces     = 6
	wordBytes    = 8
)

// Seed is a game seed: 96 bytes, written as 192 hex characters.
type Seed [SeedBytes]byte

// SeedLengthError reports a seed string that is not 192 characters long.
type SeedLengthError struct {
	Length int
}

func (e SeedLengthError) Error() string {
	return "a seed is " + strconv.Itoa(2*SeedBytes) + " hex characters, got " + strconv.Itoa(e.Length)
}

// SeedNotHexError reports a seed string holding a character that is not a hex digit.
type SeedNotHexError struct{}

func (SeedNotHexError) Error() string {
	return "a seed holds only hex characters"
}

// ParseSeed reads 192 hex digits, upper or lower case, with nothing around them. The length is
// counted in bytes.
func ParseSeed(hex string) (Seed, error) {
	if len(hex) != 2*SeedBytes {
		return Seed{}, SeedLengthError{Length: len(hex)}
	}

	var seed Seed
	for i := range seed {
		high, highOK := hexDigit(hex[2*i])
		low, lowOK := hexDigit(hex[2*i+1])
		if !highOK || !lowOK {
			return Seed{}, SeedNotHexError{}
		}

		seed[i] = high<<4 | low
	}

	return seed, nil
}

func hexDigit(digit byte) (byte, bool) {
	switch {
	case '0' <= digit && digit <= '9':
		return digit - '0', true
	case 'a' <= digit && digit <= 'f':
		return digit - 'a' + 10, true
	case 'A' <= digit && digit <= 'F':
		return digit - 'A' + 10, true
	}

	return 0, false
}

// String returns the canonical form: 192 lowercase hex digits.
func (s Seed) String() string {
	return fmt.Sprintf("%x", s[:])
}

func RoundWall(seed Seed, roundNumber uint32) ([tile.TileIDCount]tile.TileID, tile.Dice) {
	round := []byte{byte(roundNumber), byte(roundNumber >> 8), byte(roundNumber >> 16), byte(roundNumber >> 24)}
	words := newWordStream(wallDomain, seed[:], round)

	tiles := tile.AllTileIDs()
	shuffle(tiles[:], words.next)

	return tiles, rollDice(words.next)
}

func FirstDealer(seed Seed) (dealer tile.Seat, first, second tile.Dice) {
	words := newWordStream(dealerDomain, seed[:])
	seats := tile.Seats()

	first = rollDice(words.next)
	thrower := seats[(first.Sum()-1)%tile.SeatCount]

	second = rollDice(words.next)
	dealer = seats[(thrower.Index()+second.Sum()-1)%tile.SeatCount]

	return dealer, first, second
}

// SeatPermutation returns the seed's permutation of the four seats. ronin seats its k players at
// the first k entries, in the order they joined.
func SeatPermutation(seed Seed) [tile.SeatCount]tile.Seat {
	seats := tile.Seats()
	shuffle(seats[:], newWordStream(seatDomain, seed[:]).next)
	return seats
}

type wordStream struct {
	shake *sha3.SHAKE
}

func newWordStream(domain string, data ...[]byte) wordStream {
	shake := sha3.NewSHAKE256()
	_, _ = shake.Write([]byte(domain))
	for _, part := range data {
		_, _ = shake.Write(part)
	}

	return wordStream{shake: shake}
}

func (s wordStream) next() uint64 {
	var word [wordBytes]byte
	_, _ = s.shake.Read(word[:])
	var n uint64
	for i := len(word) - 1; i >= 0; i-- {
		n = n<<8 | uint64(word[i])
	}

	return n
}

func bounded(next func() uint64, bound uint64) uint64 {
	topBucket := bits.Rem64(1, 0, bound)
	for {
		word := next()
		if word <= math.MaxUint64-topBucket {
			return word % bound
		}
	}
}

func shuffle[T any](items []T, next func() uint64) {
	for i := range len(items) - 1 {
		offset := int(bounded(next, uint64(len(items)-i)))
		items[i], items[i+offset] = items[i+offset], items[i]
	}
}

func rollDice(next func() uint64) tile.Dice {
	first := int(bounded(next, dieFaces)) + 1
	second := int(bounded(next, dieFaces)) + 1
	return tile.Dice{First: first, Second: second}
}
