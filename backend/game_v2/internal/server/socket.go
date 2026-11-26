package server

import (
	"bytes"
	"context"
	"net/http"
	"runtime/debug"
	"sync"
	"time"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	logConnected        = "websocket connected"
	logDisconnected     = "websocket disconnected"
	logAcceptFailed     = "websocket peer gone before its accept"
	logDecodeError      = "decode error"
	logTooManyDecodes   = "too many decode errors, disconnecting"
	logMessageLoopFails = "websocket message loop failed"
)

const (
	undecodableReason   = "Undecodable message"
	tooManyMessages     = "Too many messages"
	tooManyResyncs      = "Too many resync requests"
	decodeErrorsReason  = "too_many_decode_errors"
	internalErrorReason = "internal_error"
	closeTooManyDecodes = session.CloseCode(4004)
	noCloseStatus       = websocket.StatusCode(-1)
	textFrameErrorType  = "text_frame"
	msgpackErrorType    = "msgpack"
)

const maxIdleReadBufferCapacity = 4 << 10

func (s *Server) serveSocket(w http.ResponseWriter, r *http.Request) {
	gameID := r.PathValue("game_id")
	if !replayfile.IsValidGameID(gameID) {
		http.Error(w, "invalid_game_id", http.StatusForbidden)
		return
	}

	ws, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
		CompressionMode:    websocket.CompressionDisabled,
	})
	if err != nil {
		s.log.Info(logAcceptFailed, "game_id", gameID, "error", err)
		return
	}

	ws.SetReadLimit(wire.MaxMessageBytes)

	conn := newConnection(ws, gameID, s)
	if !s.track(conn) {
		_ = ws.Close(websocket.StatusServiceRestart, "")
		return
	}
	defer s.untrack(conn)

	s.stats.accepted.Add(1)
	s.stats.connections.Add(1)
	defer s.stats.connections.Add(-1)
	s.serveConnection(r.Context(), conn)
}

func (s *Server) serveConnection(ctx context.Context, conn *connection) {
	stopClosingOnCancel := context.AfterFunc(ctx, func() { _ = conn.ws.CloseNow() })
	defer stopClosingOnCancel()

	var helpers sync.WaitGroup
	helpers.Go(func() { conn.write(ctx) })
	helpers.Go(func() { conn.ping(ctx, s.cfg.Socket.PingInterval, s.cfg.Socket.PingTimeout) })
	defer helpers.Wait()
	defer conn.stopWriter()

	conn.log.Info(logConnected)
	s.cfg.Session.Connect(conn)
	closeCode := s.readMessages(context.WithoutCancel(ctx), conn)
	conn.log.Info(logDisconnected, "close_code", closeCode)
	s.cfg.Session.Disconnect(conn)
}

type reader struct {
	s       *Server
	conn    *connection
	budget  tokenBucket
	resyncs tokenBucket
	strikes int
}

func (s *Server) readMessages(ctx context.Context, conn *connection) websocket.StatusCode {
	now := s.cfg.Now()
	rd := reader{
		s:       s,
		conn:    conn,
		budget:  newTokenBucket(s.cfg.Socket.Rate, s.cfg.Socket.Burst, now),
		resyncs: newTokenBucket(s.cfg.Socket.ResyncRate, s.cfg.Socket.ResyncBurst, now),
	}
	var readBuffer bytes.Buffer
	for {
		typ, data, err := readFrame(ctx, conn.ws, &readBuffer)
		if err != nil {
			return websocket.CloseStatus(err)
		}

		if !rd.handleFrame(typ, data) {
			return noCloseStatus
		}

		if readBuffer.Cap() > maxIdleReadBufferCapacity {
			readBuffer = bytes.Buffer{}
		}
	}
}

func readFrame(ctx context.Context, ws *websocket.Conn, readBuffer *bytes.Buffer) (websocket.MessageType, []byte, error) {
	readBuffer.Reset()
	typ, r, err := ws.Reader(ctx)
	if err != nil {
		return 0, nil, err
	}

	_, err = readBuffer.ReadFrom(r)
	return typ, readBuffer.Bytes(), err
}

func (rd *reader) handleFrame(typ websocket.MessageType, data []byte) (keepReading bool) {
	defer func() {
		if r := recover(); r != nil {
			rd.conn.log.Error(logMessageLoopFails, "panic", r, "stack", string(debug.Stack()))
			rd.conn.Close(session.CloseInternalError, internalErrorReason)
			keepReading = false
		}
	}()

	received := rd.s.cfg.Now()
	stats := &rd.s.stats
	stats.countIn(len(data))

	m, errorType := decodeFrame(typ, data)
	if errorType != "" {
		return rd.strike(received, errorType)
	}

	rd.strikes = 0

	if !rd.budget.take(received) {
		stats.rateLimited.Add(1)
		waitID, named := messaging.RefusedWaitID(m)
		rd.s.send(rd.conn, messaging.SessionError(
			messaging.SessionRateLimited, tooManyMessages, play.Option[int]{Value: waitID, OK: named},
		))
		return true
	}

	if rd.answeredBeforeRouting(m, received) {
		return true
	}

	rd.s.router.Route(rd.conn, m)
	stats.countHandled(rd.s.cfg.Now().Sub(received))
	return true
}

func decodeFrame(typ websocket.MessageType, data []byte) (wire.Map, string) {
	if typ != websocket.MessageBinary {
		return nil, textFrameErrorType
	}

	m, err := wire.Decode(data)
	if err != nil {
		return nil, msgpackErrorType
	}

	return m, ""
}

func (rd *reader) strike(at time.Time, errorType string) bool {
	rd.s.stats.malformed.Add(1)
	rd.strikes++
	if rd.budget.take(at) {
		rd.conn.log.Warn(logDecodeError, "error_type", errorType, "strikes", rd.strikes)
		rd.s.send(rd.conn, messaging.SessionError(
			messaging.SessionInvalidMessage, undecodableReason, play.Option[int]{},
		))
	} else {
		rd.s.stats.rateLimited.Add(1)
	}

	if rd.strikes < rd.s.cfg.Socket.MaxDecodeErrors {
		return true
	}

	rd.conn.log.Info(logTooManyDecodes)
	rd.conn.Close(closeTooManyDecodes, decodeErrorsReason)
	return false
}

func (rd *reader) answeredBeforeRouting(m wire.Map, at time.Time) bool {
	typ, _ := m.Get(wire.KeyEventType)
	switch typ {
	case wire.Int(messaging.ClientPing):
		rd.s.send(rd.conn, messaging.Pong())
		return true
	case wire.Int(messaging.ClientResync):
		if rd.resyncs.take(at) {
			return false
		}

		rd.s.stats.rateLimited.Add(1)
		rd.s.send(rd.conn, messaging.SessionError(messaging.SessionRateLimited, tooManyResyncs, play.Option[int]{}))
		return true
	}

	return false
}

func (s *Server) send(conn *connection, m wire.Map) {
	sendMessage(conn.log, conn, m)
}
