// Package meld holds the shapes of declared melds: tile groups called from another seat's
// discard, or a concealed kan, built only from tiles that fit their kind. It reads the melds the
// table sees as those shapes, and checks the hand and melds a rule helper is given.
//
// Ported from the meld module of mahjong-rs's mahjong-core, with the core meld of a meld view and
// the hand input check from the event module of its mahjong-game.
package meld

import (
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Kind is what a meld is.
type Kind uint8

// The meld kinds. An open kan is called from a discard or added to a pon; a closed kan is declared
// from four concealed tiles.
const (
	Chi Kind = iota
	Pon
	OpenKan
	ClosedKan
)

// String names k: "chi", "pon", "open kan" or "closed kan".
func (k Kind) String() string {
	switch k {
	case Chi:
		return "chi"
	case Pon:
		return "pon"
	case OpenKan:
		return "open kan"
	case ClosedKan:
		return "closed kan"
	default:
		return "meld.Kind(" + strconv.Itoa(int(k)) + ")"
	}
}

// NotASequenceError reports chi tiles that are not three consecutive tiles of one suit.
type NotASequenceError struct{}

func (NotASequenceError) Error() string {
	return "a chi needs three consecutive tiles of one suit"
}

// NotOneKindError reports pon or kan tiles that are not all of one kind.
type NotOneKindError struct{}

func (NotOneKindError) Error() string {
	return "a pon or kan needs tiles of one kind"
}

// Meld is a meld whose tiles fit its kind. A chi keeps its tiles in ascending order, the others in
// the order given.
type Meld struct {
	kind  Kind
	tiles [4]tile.Tile
}

// NewChi returns the chi of tiles, sorted; a NotASequenceError unless the tiles, in any order, are
// three consecutive tiles of one suit.
func NewChi(tiles [3]tile.Tile) (Meld, error) {
	slices.SortFunc(tiles[:], tile.Tile.Compare)
	first, second, third := tiles[0].Kind(), tiles[1].Kind(), tiles[2].Kind()
	isSequence := !first.IsHonor() && first.Simplify() <= 6 && second == first+1 && third == first+2
	if !isSequence {
		return Meld{}, NotASequenceError{}
	}
	return withTiles(Chi, tiles[:]), nil
}

// NewPon returns the pon of tiles; a NotOneKindError unless the three tiles are of one kind.
func NewPon(tiles [3]tile.Tile) (Meld, error) {
	return ofOneKind(Pon, tiles[:])
}

// NewOpenKan returns the open kan of tiles; a NotOneKindError unless the four tiles are of one
// kind.
func NewOpenKan(tiles [4]tile.Tile) (Meld, error) {
	return ofOneKind(OpenKan, tiles[:])
}

// NewClosedKan returns the closed kan of tiles; a NotOneKindError unless the four tiles are of one
// kind.
func NewClosedKan(tiles [4]tile.Tile) (Meld, error) {
	return ofOneKind(ClosedKan, tiles[:])
}

func ofOneKind(kind Kind, tiles []tile.Tile) (Meld, error) {
	first := tiles[0].Kind()
	for _, t := range tiles {
		if t.Kind() != first {
			return Meld{}, NotOneKindError{}
		}
	}
	return withTiles(kind, tiles), nil
}

func withTiles(kind Kind, tiles []tile.Tile) Meld {
	stored := [4]tile.Tile{tiles[0], tiles[0], tiles[0], tiles[0]}
	copy(stored[:], tiles)
	return Meld{kind: kind, tiles: stored}
}

// Kind returns m's kind.
func (m Meld) Kind() Kind {
	return m.kind
}

// Tiles returns m's three tiles, or four for a kan, as a copy.
func (m Meld) Tiles() []tile.Tile {
	if m.IsKan() {
		return m.tiles[:]
	}
	return m.tiles[:3]
}

// IsOpen reports whether m opens the hand: every meld but a closed kan does.
func (m Meld) IsOpen() bool {
	return m.kind != ClosedKan
}

// IsKan reports whether m is an open or a closed kan.
func (m Meld) IsKan() bool {
	return m.kind == OpenKan || m.kind == ClosedKan
}

// FirstKind returns the lowest kind of m.
func (m Meld) FirstKind() tile.Kind {
	return m.tiles[0].Kind()
}

// String returns m's kind and tiles in mpsz, such as "chi 406m" or "closed kan 1111z".
func (m Meld) String() string {
	return m.kind.String() + " " + tile.TilesString(m.Tiles())
}
