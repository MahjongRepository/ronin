package tile

const SeatCount = 4

// Seat is an absolute seat, 0 to 3, counted counter-clockwise: the seat after seat n in turn
// order is n + 1, wrapping to 0. Its zero value is seat 0.
type Seat struct {
	n uint8
}

// NewSeat returns seat n; false when n is not 0 to 3.
func NewSeat(n int) (Seat, bool) {
	if n < 0 || n >= SeatCount {
		return Seat{}, false
	}

	return Seat{n: uint8(n)}, true
}

// Seats returns the four seats in order.
func Seats() [SeatCount]Seat {
	return [SeatCount]Seat{{0}, {1}, {2}, {3}}
}

// Index returns the seat number, an index into per-seat arrays.
func (s Seat) Index() int {
	return int(s.n)
}

// Next returns the seat that plays after s (shimocha).
func (s Seat) Next() Seat {
	return Seat{n: (s.n + 1) % SeatCount}
}

// Kamicha returns the seat that plays before s, whose discards s may chi.
func (s Seat) Kamicha() Seat {
	return Seat{n: (s.n + SeatCount - 1) % SeatCount}
}

// DistanceFrom returns how many turns after from s plays: 0 for the same seat, 1 for its
// shimocha, 3 for its kamicha.
func (s Seat) DistanceFrom(from Seat) int {
	return int((s.n + SeatCount - from.n) % SeatCount)
}

// Wind returns s's wind in a round dealer deals: East for the dealer, then South, West and North
// in turn order.
func (s Seat) Wind(dealer Seat) Wind {
	return Wind(s.DistanceFrom(dealer))
}
