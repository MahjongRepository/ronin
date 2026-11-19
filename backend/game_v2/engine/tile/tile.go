package tile

// AkaDora says whether the red fives are told apart from the other fives.
type AkaDora uint8

// The two ways to read the red fives.
const (
	AkaDoraDisabled AkaDora = iota
	AkaDoraEnabled
)

const redFiveCodeStart = KindCount

// Tile is one tile of a hand: a kind, and for a five of a suit whether it is the red five. Its
// zero value is the plain 1m.
type Tile struct {
	code uint8
}

// NewTile returns the plain tile of kind; false when kind is past the last kind.
func NewTile(kind Kind) (Tile, bool) {
	if kind >= KindCount {
		return Tile{}, false
	}
	return Tile{code: uint8(kind)}, true
}

// RedFive returns the red five of kind's suit; false unless kind is a five of a suit: 4, 13 or 22.
func RedFive(kind Kind) (Tile, bool) {
	if kind.IsHonor() || kind%9 != 4 {
		return Tile{}, false
	}
	return redFiveOfSuit(int(kind / 9)), true
}

func redFiveOfSuit(suit int) Tile {
	return Tile{code: uint8(redFiveCodeStart + suit)}
}

// Kind returns t's kind, a red five counting as its five.
func (t Tile) Kind() Kind {
	if t.IsRed() {
		return Kind(t.code-redFiveCodeStart)*9 + 4
	}
	return Kind(t.code)
}

// IsRed reports whether t is a red five.
func (t Tile) IsRed() bool {
	return t.code >= redFiveCodeStart
}

// IsMan reports whether t is of the man suit, 1m to 9m.
func (t Tile) IsMan() bool {
	return t.Kind() < 9
}

// IsPin reports whether t is of the pin suit, 1p to 9p.
func (t Tile) IsPin() bool {
	kind := t.Kind()
	return kind >= 9 && kind < 18
}

// IsSou reports whether t is of the sou suit, 1s to 9s.
func (t Tile) IsSou() bool {
	kind := t.Kind()
	return kind >= 18 && kind < HonorStart
}

// IsHonor reports whether t is a wind or a dragon, 1z to 7z.
func (t Tile) IsHonor() bool {
	return t.Kind().IsHonor()
}

// IsTerminal reports whether t is a one or a nine of a suit.
func (t Tile) IsTerminal() bool {
	return t.Kind().IsTerminal()
}

// IsTerminalOrHonor reports whether t is a terminal or an honor.
func (t Tile) IsTerminalOrHonor() bool {
	return t.Kind().IsTerminalOrHonor()
}

// Compare orders tiles by kind, a red five just before the plain fives of its suit. It returns -1,
// 0 or +1, as cmp.Compare does.
func (t Tile) Compare(u Tile) int {
	switch {
	case t.Kind() < u.Kind():
		return -1
	case t.Kind() > u.Kind():
		return 1
	case t.IsRed() == u.IsRed():
		return 0
	case t.IsRed():
		return -1
	}
	return 1
}

// String returns t in mpsz notation: "1m", "0p" for the red five of pin, "7z" for Chun.
func (t Tile) String() string {
	rank, suit := t.rankAndSuit()
	return string([]byte{rank, suit})
}

func (t Tile) rankAndSuit() (rank, suit byte) {
	kind := t.Kind()
	suit = "mpsz"[kind/9]
	if t.IsRed() {
		return '0', suit
	}
	return '1' + byte(kind.Simplify()), suit
}
