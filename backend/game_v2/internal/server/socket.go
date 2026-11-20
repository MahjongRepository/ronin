package server

import (
	"context"
	"errors"
	"net/http"
	"sync"
	"time"

	"github.com/coder/websocket"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	logConnected        = "websocket connected"
	logDisconnected     = "websocket disconnected"
	logAcceptFailed     = "websocket peer gone before its accept"
	logDecodeError      = "decode error"
	logTooManyDecodes   = "too many decode errors, disconnecting"
	logInvalidMessage   = "invalid message"
	logInvalidTicket    = "invalid game ticket"
	logTicketMismatch   = "ticket game_id mismatch"
	logMessageLoopFails = "websocket message loop failed"
	logEncodeFailed     = "encode message"
)

const (
	undecodableReason    = "Undecodable message"
	invalidMessageReason = "Invalid message"
	tooManyMessages      = "Too many messages"
	tooManyResyncs       = "Too many resync requests"
	decodeErrorsReason   = "too_many_decode_errors"
	internalErrorReason  = "internal_error"
	closeTooManyDecodes  = session.CloseCode(4004)
	noCloseStatus        = websocket.StatusCode(-1)
	textFrameErrorType   = "text_frame"
	msgpackErrorType     = "msgpack"
)

func (s *Server) serveSocket(w http.ResponseWriter, r *http.Request) {
	gameID := r.PathValue("game_id")
	if !store.IsValidGameID(gameID) {
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
	var helpers sync.WaitGroup
	helpers.Go(func() { conn.write(ctx) })
	helpers.Go(func() { conn.ping(ctx, s.cfg.Socket.PingInterval, s.cfg.Socket.PingTimeout) })
	defer helpers.Wait()
	defer conn.stopWriter()

	conn.log.Info(logConnected)
	s.cfg.Session.Connect(conn)
	closeCode := s.readMessages(ctx, conn)
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
	now := time.Now()
	rd := reader{
		s:       s,
		conn:    conn,
		budget:  newTokenBucket(s.cfg.Socket.Rate, s.cfg.Socket.Burst, now),
		resyncs: newTokenBucket(s.cfg.Socket.ResyncRate, s.cfg.Socket.ResyncBurst, now),
	}
	for {
		typ, data, err := conn.ws.Read(ctx)
		if err != nil {
			return websocket.CloseStatus(err)
		}
		if !rd.handleFrame(typ, data) {
			return noCloseStatus
		}
	}
}

func (rd *reader) handleFrame(typ websocket.MessageType, data []byte) (keepReading bool) {
	defer func() {
		if r := recover(); r != nil {
			rd.conn.log.Error(logMessageLoopFails, "panic", r)
			rd.conn.Close(session.CloseInternalError, internalErrorReason)
			keepReading = false
		}
	}()

	received := time.Now()
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

	rd.s.route(rd.conn, m)
	stats.countHandled(time.Since(received))
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

func (s *Server) route(conn *connection, m wire.Map) {
	message, err := messaging.ParseClientMessage(m)
	if err != nil {
		s.stats.malformed.Add(1)
		conn.log.Warn(logInvalidMessage, "error_type", invalidMessageType(err))
		s.send(conn, messaging.SessionError(messaging.SessionInvalidMessage, invalidMessageReason, play.Option[int]{}))
		return
	}

	switch msg := message.(type) {
	case messaging.GameActionMessage:
		s.dispatch(func() { s.cfg.Session.Act(conn, msg) })
	case messaging.JoinGameMessage:
		if s.verifiedTicket(conn, msg.Ticket) {
			s.dispatch(func() { s.cfg.Session.Join(conn, msg.Ticket) })
		}
	case messaging.ReconnectMessage:
		if s.verifiedTicket(conn, msg.Ticket) {
			s.dispatch(func() { s.cfg.Session.Reconnect(conn, msg.Ticket) })
		}
	case messaging.ResyncMessage:
		s.dispatch(func() { s.cfg.Session.Resync(conn) })
	}
}

func invalidMessageType(err error) string {
	if invalid, ok := errors.AsType[messaging.InvalidMessageError](err); ok {
		return invalid.Reason
	}
	return "unknown"
}

func (s *Server) dispatch(call func()) {
	began := time.Now()
	call()
	s.lag.observe(began, time.Since(began))
}

func (s *Server) verifiedTicket(conn *connection, token string) bool {
	ticket, err := auth.VerifyTicket(token, s.cfg.TicketSecret, time.Now())
	switch {
	case err != nil:
		conn.log.Warn(logInvalidTicket, "error", err)
		s.sendTicketError(conn, "Invalid game ticket")
		return false
	case ticket.RoomID != conn.GameID():
		conn.log.Warn(logTicketMismatch, "ticket_room_id", ticket.RoomID, "expected_game_id", conn.GameID())
		s.sendTicketError(conn, "Ticket game_id mismatch")
		return false
	}
	return true
}

func (s *Server) sendTicketError(conn *connection, message string) {
	s.send(conn, messaging.SessionError(messaging.SessionInvalidTicket, message, play.Option[int]{}))
}

func (s *Server) send(conn *connection, m wire.Map) {
	data, err := wire.Encode(m)
	if err != nil {
		conn.log.Error(logEncodeFailed, "error", err)
		return
	}
	conn.Send(data)
}
