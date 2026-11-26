package session

import (
	"math"
	"math/rand/v2"
	"slices"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	discardHoldFloor     = 150 * time.Millisecond
	discardHoldPauseMode = 950 * time.Millisecond
	discardHoldPauseMax  = 2100 * time.Millisecond
	discardHoldPauseRate = 0.08
)

func RandomDiscardHold() time.Duration {
	return discardHoldOf(rand.Float64(), rand.Float64())
}

// RandomPick returns a random index below n, for Config.Pick. It is safe for concurrent use and
// independent of every game's seed.
func RandomPick(n int) int {
	return rand.IntN(n)
}

func discardHoldOf(roll, shape float64) time.Duration {
	if roll >= discardHoldPauseRate {
		return discardHoldFloor
	}

	span := float64(discardHoldPauseMax - discardHoldFloor)
	rise := float64(discardHoldPauseMode - discardHoldFloor)
	if shape < rise/span {
		return discardHoldFloor + time.Duration(math.Sqrt(shape*span*rise))
	}
	fall := float64(discardHoldPauseMax - discardHoldPauseMode)
	return discardHoldPauseMax - time.Duration(math.Sqrt((1-shape)*span*fall))
}

type discardHold struct {
	floor   time.Time
	until   time.Time
	release delayed
	shown   []play.Emitted
	kept    []play.Emitted
	actor   play.Option[tile.Seat]
}

func (h *discardHold) held() bool {
	return h.release.armed
}

func (h *discardHold) drop() {
	h.release.cancel()
	*h = discardHold{release: h.release}
}

func startsHold(emitted play.Emitted) bool {
	if _, discarded := emitted.Event.(play.Discarded); discarded {
		return true
	}
	called, ok := emitted.Event.(play.Called)
	return ok && (called.Meld.Kind == play.MeldClosedKan || called.Meld.Kind == play.MeldAddedKan)
}

func furitenAhead(events []play.Emitted) []play.Emitted {
	isFuriten := func(e play.Emitted) bool {
		_, furiten := e.Event.(play.FuritenChanged)
		return furiten
	}
	if !slices.ContainsFunc(events, isFuriten) {
		return events
	}

	shown, kept := splitAtHoldStart(events, slices.IndexFunc(events, startsHold))
	return append(shown, kept...)
}

func splitAtHoldStart(events []play.Emitted, start int) (shown, kept []play.Emitted) {
	withDora := false
	if start >= 0 {
		_, withDora = events[start].Event.(play.Discarded)
	}

	shown = slices.Clone(events[:start+1])
	for _, e := range events[start+1:] {
		if showsAtOnce(e, withDora) {
			shown = append(shown, e)
		} else {
			kept = append(kept, e)
		}
	}
	return shown, kept
}

func showsAtOnce(emitted play.Emitted, withDora bool) bool {
	_, furiten := emitted.Event.(play.FuritenChanged)
	_, dora := emitted.Event.(play.DoraRevealed)
	return furiten || (dora && withDora)
}

func (g *game) heldPart(events []play.Emitted) (shown, kept []play.Emitted, holds bool) {
	sample := g.m.cfg.DiscardHold
	if sample == nil {
		return nil, nil, false
	}

	now := g.clock.Now()
	start := slices.IndexFunc(events, startsHold)
	if start >= 0 {
		g.hold.floor = now.Add(discardHoldFloor)
		g.hold.until = now.Add(max(discardHoldFloor, sample()))
	}
	_, callOpen := g.engine.Awaiting().(play.AwaitingCall)
	if callOpen || !now.Before(g.hold.until) {
		return nil, nil, false
	}
	shown, kept = splitAtHoldStart(events, start)
	return shown, kept, true
}

func (g *game) holdUpdate(shown, kept []play.Emitted, actor play.Option[tile.Seat]) error {
	g.asked.invalidate()
	for _, p := range g.participants {
		p.timer.stop()
	}
	if len(shown) > 0 {
		err := g.sendEvents(shown, nil, g.lazyTable())
		if err != nil {
			return err
		}
	}

	g.hold.shown, g.hold.kept, g.hold.actor = shown, kept, actor
	g.hold.release.arm(g.clock, g.hold.until.Sub(g.clock.Now()), func(token uint64) {
		g.post(func() {
			g.guard("discard hold failed", func() error { return g.holdDue(token) })
		})
	})
	return nil
}

func (g *game) holdDue(token uint64) error {
	if !g.hold.release.claim(token) {
		return nil
	}
	return g.showHeld()
}

func (g *game) holdsGameEnd() bool {
	_, over := g.engine.Awaiting().(play.AwaitingGameOver)
	return over && g.hold.held()
}

func (g *game) showHeld() error {
	kept, actor := g.hold.kept, g.hold.actor
	g.hold.drop()
	return g.showUpdate(kept, actor)
}

func (g *game) shownView(seat tile.Seat) play.SeatView {
	if !g.hold.held() {
		return g.engine.View(seat)
	}

	view := g.published.View(seat)
	view.Decision = play.Option[play.Decision]{}
	for _, e := range g.hold.shown {
		view.Record = engine.Follow(view.Record, e)
	}
	return view
}
