package session

import (
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
)

type timeoutKind uint8

const (
	timeoutTurn timeoutKind = iota
	timeoutMeld
	timeoutPause
)

type delayed struct {
	stop  func() bool
	token uint64
	armed bool
}

func (d *delayed) arm(clock Clock, after time.Duration, fire func(token uint64)) {
	d.cancel()
	d.token++
	token := d.token
	d.armed = true
	d.stop = clock.AfterFunc(after, func() { fire(token) })
}

func (d *delayed) cancel() {
	if d.armed {
		d.stop()
	}
	d.armed = false
}

func (d *delayed) claim(token uint64) bool {
	if !d.armed || token != d.token {
		return false
	}
	d.armed = false
	return true
}

type turnTimer struct {
	timing    *Timing
	clock     Clock
	bank      time.Duration
	running   delayed
	startedAt time.Time
	charging  bool
	suspended play.Option[time.Time]
}

func newTurnTimer(timing *Timing, clock Clock) turnTimer {
	return turnTimer{timing: timing, clock: clock, bank: timing.InitialBank}
}

func (t *turnTimer) resetBank() {
	t.bank = t.timing.InitialBank
}

func (t *turnTimer) startDecision(fire func(token uint64)) {
	t.startedAt, t.charging = t.clock.Now(), true
	t.running.arm(t.clock, t.timing.BaseTurn+t.bank, fire)
}

func (t *turnTimer) startFixed(after time.Duration, fire func(token uint64)) {
	t.startedAt, t.charging = t.clock.Now(), false
	t.running.arm(t.clock, after, fire)
}

func (t *turnTimer) elapsed() play.Option[float64] {
	if !t.running.armed {
		return play.Option[float64]{}
	}
	return play.Some(t.clock.Now().Sub(t.startedAt).Seconds())
}

func (t *turnTimer) suspend() {
	if !t.charging || !t.running.armed {
		t.stop()
		return
	}
	t.running.cancel()
	t.suspended = play.Some(t.clock.Now())
}

func (t *turnTimer) resume(fire func(token uint64)) {
	t.suspended = play.Option[time.Time]{}
	deadline := t.startedAt.Add(t.timing.BaseTurn + t.bank)
	t.running.arm(t.clock, max(0, deadline.Sub(t.clock.Now())), fire)
}

func (t *turnTimer) stop() {
	t.running.cancel()
	if !t.charging {
		return
	}
	end := t.clock.Now()
	if t.suspended.OK {
		end = t.suspended.Value
	}
	overtime := max(0, end.Sub(t.startedAt)-t.timing.BaseTurn)
	t.bank = max(0, t.bank-overtime)
	t.charging = false
	t.suspended = play.Option[time.Time]{}
}

func (t *turnTimer) cancel() {
	t.running.cancel()
}

func seconds(d time.Duration) messaging.Seconds {
	if d%time.Second == 0 {
		return messaging.WholeSeconds(int(d / time.Second))
	}
	return messaging.FractionalSeconds(d.Seconds())
}
