package seam_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

const xorshiftNonzeroState uint64 = 0x9E3779B97F4A7C15

type agent interface {
	observe(event play.Emitted) error
	decide(decision play.Decision) (play.Action, error)
}

type tsumogiri struct{}

func (tsumogiri) observe(play.Emitted) error {
	return nil
}

func (tsumogiri) decide(decision play.Decision) (play.Action, error) {
	for _, win := range []play.Action{play.TsumoAction(), play.RonAction()} {
		if slices.Contains(decision.Legal, win) {
			return win, nil
		}
	}
	return decision.Default, nil
}

type randomLegal struct {
	state uint64
}

func newRandomLegal(seed uint64) *randomLegal {
	if seed == 0 {
		return &randomLegal{state: xorshiftNonzeroState}
	}
	return &randomLegal{state: seed}
}

func (r *randomLegal) nextWord() uint64 {
	r.state ^= r.state << 13
	r.state ^= r.state >> 7
	r.state ^= r.state << 17
	return r.state
}

func (*randomLegal) observe(play.Emitted) error {
	return nil
}

func (r *randomLegal) decide(decision play.Decision) (play.Action, error) {
	return decision.Legal[r.nextWord()%uint64(len(decision.Legal))], nil
}

func TestTsumogiri_WhenOfferedAWin_ShouldTakeItAndElsePlayTheDefault(t *testing.T) {
	held := copyOf(t, 0, "1m")
	turn := play.Decision{
		Seat:    seat(t, 0),
		Context: play.TurnAfterDraw{Drawn: held},
		Legal:   []play.Action{play.DiscardAction(held), play.TsumoAction()},
		Default: play.DiscardAction(held),
	}
	call, ok := threePinWithTwoRonCallers(t).Decision(seat(t, 0))
	if !ok {
		t.Fatal("seat 0 is not prompted")
	}
	quietTurn := turn
	quietTurn.Legal = []play.Action{play.DiscardAction(held)}

	var picks [3]play.Action
	for i, decision := range []play.Decision{turn, call, quietTurn} {
		picks[i], _ = tsumogiri{}.decide(decision)
	}

	assertEqual(t, "picks", picks, [3]play.Action{play.TsumoAction(), play.RonAction(), play.DiscardAction(held)})
}
