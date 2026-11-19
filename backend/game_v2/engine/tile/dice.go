package tile

// Dice are two dice as thrown, each 1 to 6.
type Dice struct {
	First, Second int
}

// Sum returns the sum of the two dice.
func (d Dice) Sum() int {
	return d.First + d.Second
}
