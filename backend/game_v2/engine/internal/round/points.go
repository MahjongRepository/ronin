package round

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Points is the table's points ledger: each seat's score and the riichi sticks on the table. It
// is a value; its zero value is every score at 0 with no stick.
type Points struct {
	scores       [tile.SeatCount]int
	riichiSticks int
}

// NewPoints returns the ledger of scores with riichiSticks on the table.
func NewPoints(scores [tile.SeatCount]int, riichiSticks int) Points {
	return Points{scores: scores, riichiSticks: riichiSticks}
}

// Score returns the score of seat.
func (p Points) Score(seat tile.Seat) int {
	return p.scores[seat.Index()]
}

// Scores returns every score, by seat.
func (p Points) Scores() [tile.SeatCount]int {
	return p.scores
}

// RiichiSticks returns the riichi sticks on the table.
func (p Points) RiichiSticks() int {
	return p.riichiSticks
}

// Total returns the points of the scores and the riichi sticks together.
func (p Points) Total() int {
	total := p.riichiSticks * rules.RiichiStickValue
	for _, score := range p.scores {
		total += score
	}

	return total
}

func (p *Points) depositRiichi(seat tile.Seat) play.Emitted {
	p.scores[seat.Index()] -= rules.RiichiCost
	p.riichiSticks++
	return toAll(play.RiichiDeposited{Seat: seat, Score: p.Score(seat), RiichiSticks: p.riichiSticks})
}

// ApplyChanges adds changes to the scores, by seat.
func (p *Points) ApplyChanges(changes [tile.SeatCount]int) {
	for seat, change := range changes {
		p.scores[seat] += change
	}
}

// ClearSticks takes the riichi sticks off the table, as a win does once its payments hold them.
func (p *Points) ClearSticks() {
	p.riichiSticks = 0
}

// SetFinal puts in the final scores, the riichi sticks already in them.
func (p *Points) SetFinal(scores [tile.SeatCount]int) {
	p.scores = scores
	p.riichiSticks = 0
}
