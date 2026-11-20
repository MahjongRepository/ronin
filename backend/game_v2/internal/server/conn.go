package server

import (
	"context"
	"errors"
	"log/slog"
	"runtime/debug"
	"sync"
	"sync/atomic"
	"time"
	"uuid"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
)

const sendQueueLimit = 256

const sendDueClaimedByTimer = -1

const (
	logQueueFull    = "websocket send queue full, dropping the connection"
	logSendDeadline = "websocket send blocked past its deadline, dropping the connection"
	logPeerGone     = "websocket peer gone, dropping the connection"
	logPingTimeout  = "websocket ping unanswered, dropping the connection"
)

type outgoing struct {
	data   []byte
	close  bool
	code   websocket.StatusCode
	reason string
}

type connection struct {
	id           string
	gameID       string
	ws           *websocket.Conn
	stats        *socketStats
	log          *slog.Logger
	sendDeadline time.Duration

	queue      chan outgoing
	terminated chan struct{}
	stopped    chan struct{}
	writerDone chan struct{}
	terminate  func()

	sendEpoch    time.Time
	sendTimer    *time.Timer
	sendDue      atomic.Int64
	sendTimedOut atomic.Bool

	mu     sync.Mutex
	closed bool
}

func newConnection(ws *websocket.Conn, gameID string, s *Server) *connection {
	id := uuid.New().String()
	c := &connection{
		id:           id,
		gameID:       gameID,
		ws:           ws,
		stats:        &s.stats,
		log:          s.log.With("game_id", gameID, "connection_id", id),
		sendDeadline: s.cfg.Socket.SendDeadline,
		queue:        make(chan outgoing, sendQueueLimit),
		terminated:   make(chan struct{}),
		stopped:      make(chan struct{}),
		writerDone:   make(chan struct{}),
		sendEpoch:    time.Now(),
	}
	c.terminate = sync.OnceFunc(func() {
		close(c.terminated)
		_ = c.ws.CloseNow()
	})
	return c
}

// ID returns the connection's own id, unique to it.
func (c *connection) ID() string {
	return c.id
}

// GameID returns the game id of the socket's URL.
func (c *connection) GameID() string {
	return c.gameID
}

// Send queues one encoded message; it is dropped once the connection closed or was dropped.
func (c *connection) Send(readOnlyData []byte) {
	if c.enqueue(outgoing{data: readOnlyData}) {
		c.stats.countOut(len(readOnlyData))
	}
}

// Close queues the close frame as the connection's last item; later sends and closes are dropped.
func (c *connection) Close(code session.CloseCode, reason string) {
	if c.enqueue(outgoing{close: true, code: websocket.StatusCode(code), reason: reason}) {
		c.stats.countClose(int(code))
	}
}

func (c *connection) closeForShutdown() {
	c.enqueue(outgoing{close: true, code: websocket.StatusServiceRestart})
}

func (c *connection) enqueue(item outgoing) (accepted bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed || c.isTerminated() {
		return false
	}
	c.closed = item.close
	select {
	case c.queue <- item:
		return true
	default:
		c.log.Warn(logQueueFull)
		c.terminate()
		return false
	}
}

func (c *connection) isTerminated() bool {
	select {
	case <-c.terminated:
		return true
	default:
		return false
	}
}

func (c *connection) write(ctx context.Context) {
	defer close(c.writerDone)
	defer c.recoverAndDrop("websocket writer failed")

	withoutPerFrameTimeout := context.WithoutCancel(ctx)
	for {
		select {
		case <-c.stopped:
			return
		case <-c.terminated:
			return
		case item := <-c.queue:
			if item.close {
				_ = c.ws.Close(item.code, item.reason)
				return
			}
			if !c.writeMessage(withoutPerFrameTimeout, item.data) {
				return
			}
		}
	}
}

func (c *connection) writeMessage(ctx context.Context, data []byte) bool {
	c.armSendDeadline()
	err := c.ws.Write(ctx, websocket.MessageBinary, data)
	c.disarmSendDeadline()
	if err == nil {
		return true
	}
	if c.sendTimedOut.Load() {
		c.log.Warn(logSendDeadline)
	} else {
		c.log.Info(logPeerGone)
	}
	c.terminate()
	return false
}

func (c *connection) armSendDeadline() {
	c.sendDue.Store(int64(time.Since(c.sendEpoch) + c.sendDeadline))
	if c.sendTimer == nil {
		c.sendTimer = time.AfterFunc(c.sendDeadline, c.dropIfSendOverdue)
		return
	}
	c.sendTimer.Reset(c.sendDeadline)
}

func (c *connection) disarmSendDeadline() {
	c.sendDue.Store(0)
	c.sendTimer.Stop()
}

func (c *connection) dropIfSendOverdue() {
	c.dropIfObservedSendOverdue(c.sendDue.Load(), time.Since(c.sendEpoch))
}

func (c *connection) dropIfObservedSendOverdue(observedDue int64, elapsed time.Duration) {
	if observedDue <= 0 || elapsed < time.Duration(observedDue) {
		return
	}
	if !c.sendDue.CompareAndSwap(observedDue, sendDueClaimedByTimer) {
		return
	}
	c.sendTimedOut.Store(true)
	c.terminate()
}

func (c *connection) ping(ctx context.Context, interval, timeout time.Duration) {
	defer c.recoverAndDrop("websocket pinger failed")

	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-c.stopped:
			return
		case <-c.terminated:
			return
		case <-ticker.C:
		}

		if !c.pingOnce(ctx, timeout) {
			return
		}
	}
}

func (c *connection) pingOnce(ctx context.Context, timeout time.Duration) bool {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	err := c.ws.Ping(ctx)
	if err == nil {
		return true
	}
	if errors.Is(err, context.DeadlineExceeded) {
		c.log.Info(logPingTimeout)
	}
	c.terminate()
	return false
}

func (c *connection) recoverAndDrop(message string) {
	if r := recover(); r != nil {
		c.log.Error(message, "panic", r, "stack", string(debug.Stack()))
		c.terminate()
	}
}

func (c *connection) stopWriter() {
	if c.stopSending() {
		deadline := time.NewTimer(c.sendDeadline)
		select {
		case <-c.writerDone:
		case <-c.terminated:
		case <-deadline.C:
		}
		deadline.Stop()
	}

	close(c.stopped)
	_ = c.ws.CloseNow()
	<-c.writerDone
}

func (c *connection) stopSending() (closeQueued bool) {
	c.mu.Lock()
	defer c.mu.Unlock()

	closeQueued = c.closed
	c.closed = true
	return closeQueued
}
