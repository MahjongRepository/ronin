package server

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"time"
	"uuid"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
)

const sendQueueLimit = 256

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

// connection is an accepted socket as the session sees it, written by its own writer goroutine
// from a bounded queue so no send or close waits on the client.
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
func (c *connection) Send(data []byte) {
	c.stats.countOut(len(data))
	c.enqueue(outgoing{data: data})
}

// Close queues the close frame as the connection's last item; later sends and closes are dropped.
func (c *connection) Close(code session.CloseCode, reason string) {
	c.stats.countClose(int(code))
	c.enqueue(outgoing{close: true, code: websocket.StatusCode(code), reason: reason})
}

func (c *connection) closeForShutdown() {
	c.enqueue(outgoing{close: true, code: websocket.StatusServiceRestart})
}

func (c *connection) enqueue(item outgoing) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed || c.isTerminated() {
		return
	}
	c.closed = item.close
	select {
	case c.queue <- item:
	default:
		c.log.Warn(logQueueFull)
		c.terminate()
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

func (c *connection) write() {
	defer close(c.writerDone)
	defer c.recoverAndDrop("websocket writer failed")

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
			if !c.writeMessage(item.data) {
				return
			}
		}
	}
}

func (c *connection) writeMessage(data []byte) bool {
	ctx, cancel := context.WithTimeout(context.Background(), c.sendDeadline)
	defer cancel()

	err := c.ws.Write(ctx, websocket.MessageBinary, data)
	if err == nil {
		return true
	}
	if errors.Is(err, context.DeadlineExceeded) {
		c.log.Warn(logSendDeadline)
	} else {
		c.log.Info(logPeerGone)
	}
	c.terminate()
	return false
}

func (c *connection) ping(interval, timeout time.Duration) {
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

		if !c.pingOnce(timeout) {
			return
		}
	}
}

func (c *connection) pingOnce(timeout time.Duration) bool {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
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
		c.log.Error(message, "panic", r)
		c.terminate()
	}
}

// stopWriter ends the writer once the socket stopped reading, first letting it flush a queued
// close within the send deadline so the client gets its code.
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
