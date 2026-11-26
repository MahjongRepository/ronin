package tile

// Wind is a seat or round wind.
type Wind uint8

const (
	East Wind = iota
	South
	West
	North
)

// Kind returns the kind of w's tile, 27 to 30.
func (w Wind) Kind() Kind {
	return KindEast + Kind(w)
}

// Tile returns w's honor tile.
func (w Wind) Tile() Tile {
	return Tile{code: uint8(w.Kind())}
}

// WindFromKind returns the wind of kind; false for any kind but 27 to 30.
func WindFromKind(kind Kind) (Wind, bool) {
	if kind < KindEast || kind > KindNorth {
		return East, false
	}

	return Wind(kind - KindEast), true
}
