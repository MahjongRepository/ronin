package tile

// Kind is a 34-format tile kind: man at 0 to 8, pin at 9 to 17, sou at 18 to 26 and the honors at
// 27 to 33 (East, South, West, North, Haku, Hatsu, Chun).
type Kind uint8

// The honor kinds.
const (
	KindEast Kind = 27 + iota
	KindSouth
	KindWest
	KindNorth
	KindHaku
	KindHatsu
	KindChun
)

// KindCount is the number of tile kinds.
const KindCount = 34

// HonorStart is the first honor kind.
const HonorStart = KindEast

// CopiesPerKind is the number of physical tiles of each kind in a set.
const CopiesPerKind = 4

// MaxConcealedTiles is the most tiles a concealed hand holds.
const MaxConcealedTiles = 14

// Bit masks over the 34 kinds, kind 0 the lowest bit.
const (
	TerminalMask        uint64 = 1<<0 | 1<<8 | 1<<9 | 1<<17 | 1<<18 | 1<<26
	HonorMask           uint64 = 0x7F << KindEast
	TerminalOrHonorMask        = TerminalMask | HonorMask
)

// IsHonor reports whether k is a wind or a dragon.
func (k Kind) IsHonor() bool {
	return k >= HonorStart
}

// IsTerminal reports whether k is a one or a nine of a suit.
func (k Kind) IsTerminal() bool {
	return TerminalMask>>k&1 == 1
}

// IsTerminalOrHonor reports whether k is a terminal or an honor; false for any value past the
// last kind.
func (k Kind) IsTerminalOrHonor() bool {
	return TerminalOrHonorMask>>k&1 == 1
}

// Simplify returns k's rank within its suit, 0 to 8; the honors give 0 to 6.
func (k Kind) Simplify() int {
	return int(k % 9)
}

// Mask returns the bit mask of kinds, kind 0 the lowest bit.
func Mask(kinds ...Kind) uint64 {
	var mask uint64
	for _, kind := range kinds {
		mask |= 1 << kind
	}
	return mask
}

// SuitStarts returns the first kind of man, pin and sou.
func SuitStarts() [3]Kind {
	return [3]Kind{0, 9, 18}
}

// SuitMasks returns the masks of the man, pin and sou kinds.
func SuitMasks() [3]uint64 {
	return [3]uint64{0x1FF, 0x1FF << 9, 0x1FF << 18}
}

// WindKinds returns the wind kinds, East to North.
func WindKinds() [4]Kind {
	return [4]Kind{KindEast, KindSouth, KindWest, KindNorth}
}

// DragonKinds returns the dragon kinds, Haku, Hatsu and Chun.
func DragonKinds() [3]Kind {
	return [3]Kind{KindHaku, KindHatsu, KindChun}
}

// TerminalAndHonorKinds returns the terminals of each suit, then the honors.
func TerminalAndHonorKinds() [13]Kind {
	return [13]Kind{
		0, 8, 9, 17, 18, 26,
		KindEast, KindSouth, KindWest, KindNorth, KindHaku, KindHatsu, KindChun,
	}
}
