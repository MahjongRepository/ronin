package session

import (
	"time"

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
	turnStart time.Time
	charging  bool
}

func newTurnTimer(timing *Timing, clock Clock) turnTimer {
	return turnTimer{timing: timing, clock: clock, bank: timing.InitialBank}
}

func (t *turnTimer) resetBank() {
	t.bank = t.timing.InitialBank
}

func (t *turnTimer) startDecision(fire func(token uint64)) {
	t.turnStart, t.charging = t.clock.Now(), true
	t.running.arm(t.clock, t.timing.BaseTurn+t.bank, fire)
}

func (t *turnTimer) startFixed(after time.Duration, fire func(token uint64)) {
	t.charging = false
	t.running.arm(t.clock, after, fire)
}

func (t *turnTimer) stop() {
	t.running.cancel()
	if !t.charging {
		return
	}
	overtime := max(0, t.clock.Now().Sub(t.turnStart)-t.timing.BaseTurn)
	t.bank = max(0, t.bank-overtime)
	t.charging = false
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
