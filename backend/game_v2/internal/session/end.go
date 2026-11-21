package session

import (
	"context"
	"errors"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type endReason uint8

const (
	endCompleted endReason = iota
	endAbandoned
	endFailed
)

type ending struct {
	reason     endReason
	conns      []Connection
	keepReplay bool
	records    []wire.Map
	result     play.Option[store.Result]
	endedAt    time.Time
}

func (g *game) withdraw() bool {
	if g.lifecycle != lifecyclePending || g.connectedCount() > 0 {
		g.log.Warn("withdrawn game kept, a player already joined it")
		return false
	}

	g.log.Info("pending game withdrawn")
	g.m.markWithdrawn(g.id)
	g.endGame(endAbandoned, play.Option[store.Result]{})
	return true
}

func (g *game) endGame(reason endReason, result play.Option[store.Result]) {
	if !g.active() {
		return
	}

	g.lifecycle = lifecycleEnding
	g.m.inFlight.Add(1)
	conns := make([]Connection, 0, len(g.participants))
	for p := range g.connected() {
		conns = append(conns, p.conn)
	}
	g.end = ending{reason: reason, conns: conns, result: result, endedAt: g.clock.Now()}
	if g.replay != nil && reason != endAbandoned {
		g.end.keepReplay, g.end.records = true, g.replay.Records()
	}
	g.replay = nil
	if g.observed != nil {
		g.observed.seal(g.end.endedAt)
	}

	g.m.release(g, conns)
	for _, p := range g.participants {
		p.timer.cancel()
		p.conn = nil
	}
	g.pending.cancel()
	g.aiTurn.cancel()
	g.hold.drop()
	g.asked.invalidate()
	close(g.ended)
}

func (g *game) vanish() {
	if !g.active() {
		return
	}
	g.lifecycle = lifecycleClosed
	for _, p := range g.participants {
		p.timer.cancel()
	}
	g.pending.cancel()
	g.aiTurn.cancel()
	g.hold.drop()
	g.asked.invalidate()
	close(g.ended)
}

func (g *game) finish() {
	defer g.m.inFlight.Done()

	e := g.end
	reason := e.reason
	if e.keepReplay {
		err := protect(func() error { return g.saveReplay(e.records) })
		if err != nil {
			g.log.Error("save the replay of a finished game", "error", err)
			reason = endFailed
		} else {
			g.log.Info("saved replay")
		}
	}

	if g.startRecorded {
		err := retryStoreWrite(g.m.storeCtx, g.clock, func() error { return g.recordFinish(reason, e) })
		if err != nil {
			g.log.Error("record the finish of a game", "error", err)
			reason = endFailed
		}
	}

	for _, conn := range e.conns {
		g.closeEnded(conn, reason)
	}
	g.lifecycle = lifecycleClosed
}

func (g *game) closeEnded(conn Connection, reason endReason) {
	err := protect(func() error {
		if reason == endCompleted {
			conn.Close(CloseGameEnded, "game_ended")
			return nil
		}
		return closeWithInternalError(conn)
	})
	if err != nil {
		g.log.Error("close a connection of an ended game", "error", err)
	}
}

func (g *game) saveReplay(records []wire.Map) error {
	content, err := messaging.EncodeReplayRecords(records)
	if err != nil {
		return err
	}
	return g.m.cfg.Replays.Save(g.id, content)
}

var errNoResult = errors.New("a completed game has no result")

func (g *game) recordFinish(reason endReason, e ending) error {
	db, ctx := g.m.cfg.DB, g.m.storeCtx
	switch reason {
	case endCompleted:
		if !e.result.OK {
			return errNoResult
		}
		return db.RecordCompleted(ctx, g.start, e.endedAt, e.result.Value)
	case endAbandoned:
		return db.RecordAbandoned(ctx, g.start, e.endedAt)
	case endFailed:
	}
	return db.RecordFailed(ctx, g.start, e.endedAt)
}

func closeWithInternalError(conn Connection) error {
	defer conn.Close(CloseInternalError, "internal_error")
	return send(conn, messaging.SessionError(
		messaging.SessionInternalError, "The game ended on a server error", play.Option[int]{}))
}

var storeRetryWaits = [...]time.Duration{time.Second, 2 * time.Second}

func retryStoreWrite(ctx context.Context, clock Clock, write func() error) error {
	err := protect(write)
	for _, wait := range storeRetryWaits {
		if err == nil {
			return nil
		}
		waited := make(chan struct{})
		stop := clock.AfterFunc(wait, func() { close(waited) })
		select {
		case <-waited:
		case <-ctx.Done():
			stop()
			return errors.Join(err, ctx.Err())
		}
		err = protect(write)
	}
	return err
}
