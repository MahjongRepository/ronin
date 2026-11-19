package tile

import (
	"slices"
	"strconv"
	"strings"
)

// ParseTiles parses mpsz notation such as "123m406p11z" into tiles, in the order written. Ranks
// come before their suit letter: m (man), p (pin), s (sou), z or h (honors, 1 to 7 for East
// through Chun); 0 or r in a suit is its red five. Any number of copies of a tile is accepted.
//
// The error is an InvalidCharacterError for a character that is neither a rank nor a suit letter,
// or 0 and r among honors; a TileOutOfRangeError for an honor rank of 8 or 9; a MissingSuitError
// when the string ends in ranks.
func ParseTiles(mpsz string) ([]Tile, error) {
	tiles := make([]Tile, 0, len(mpsz))
	var ranks []rune
	for _, character := range mpsz {
		suitStart, isSuit := suitStartOf(character)
		if !isSuit {
			if !isRank(character) {
				return nil, InvalidCharacterError{Character: character}
			}
			ranks = append(ranks, character)
			continue
		}
		for _, rank := range ranks {
			parsed, err := parseTile(rank, suitStart)
			if err != nil {
				return nil, err
			}
			tiles = append(tiles, parsed)
		}
		ranks = ranks[:0]
	}
	if len(ranks) > 0 {
		return nil, MissingSuitError{}
	}
	return tiles, nil
}

// ParseTile parses exactly one mpsz tile, such as "0p" for the red five of pin: the errors of
// ParseTiles, or a NotOneTileError.
func ParseTile(mpsz string) (Tile, error) {
	tiles, err := ParseTiles(mpsz)
	if err != nil {
		return Tile{}, err
	}
	if len(tiles) != 1 {
		return Tile{}, NotOneTileError{Count: len(tiles)}
	}
	return tiles[0], nil
}

func suitStartOf(character rune) (Kind, bool) {
	switch character {
	case 'm':
		return 0, true
	case 'p':
		return 9, true
	case 's':
		return 18, true
	case 'z', 'h':
		return HonorStart, true
	}
	return 0, false
}

func isRank(character rune) bool {
	return character >= '0' && character <= '9' || character == 'r'
}

func parseTile(rank rune, suitStart Kind) (Tile, error) {
	isHonor := suitStart == HonorStart
	if (rank == '0' || rank == 'r') && !isHonor {
		return redFiveOfSuit(int(suitStart / 9)), nil
	}
	if rank < '1' || rank > '9' {
		return Tile{}, InvalidCharacterError{Character: rank}
	}
	kind := suitStart + Kind(rank-'1')
	if kind >= KindCount {
		return Tile{}, TileOutOfRangeError{Character: rank}
	}
	return Tile{code: uint8(kind)}, nil
}

// TilesString writes tiles as one mpsz string, sorted, each suit followed by its letter and the
// honors by z; a red five is written as 0 before the other fives.
func TilesString(tiles []Tile) string {
	sorted := slices.Clone(tiles)
	slices.SortFunc(sorted, Tile.Compare)

	var text strings.Builder
	var openSuit byte
	for _, t := range sorted {
		rank, suit := t.rankAndSuit()
		if openSuit != 0 && openSuit != suit {
			text.WriteByte(openSuit)
		}
		text.WriteByte(rank)
		openSuit = suit
	}
	if openSuit != 0 {
		text.WriteByte(openSuit)
	}
	return text.String()
}

// InvalidCharacterError reports a character that is not a rank: anything other than 1 to 9, or 0
// and r among honors.
type InvalidCharacterError struct {
	Character rune
}

func (e InvalidCharacterError) Error() string {
	return strconv.QuoteRune(e.Character) + " is not a tile rank"
}

// TileOutOfRangeError reports a rank that gives a tile past the last tile: an honor rank of 8 or 9.
type TileOutOfRangeError struct {
	Character rune
}

func (e TileOutOfRangeError) Error() string {
	return "rank " + strconv.QuoteRune(e.Character) + " gives a tile past the last tile"
}

// MissingSuitError reports ranks at the end of the string with no suit letter after them.
type MissingSuitError struct{}

func (MissingSuitError) Error() string {
	return "the last ranks have no suit letter"
}

// NotOneTileError reports a string that parses to Count tiles where exactly one is wanted.
type NotOneTileError struct {
	Count int
}

func (e NotOneTileError) Error() string {
	return "the string holds " + strconv.Itoa(e.Count) + " tiles, not exactly one"
}
