package server

import (
	"errors"
	"log/slog"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	logInvalidMessage = "invalid message"
	logInvalidTicket  = "invalid game ticket"
	logTicketMismatch = "ticket game_id mismatch"
	logEncodeFailed   = "encode message"
)

const invalidMessageReason = "Invalid message"

// Router hands one decoded client message to the session, as a socket's reader does once the
// frame passed its rate limit and was not answered before routing (a ping, a resync over its
// budget): it parses the message, verifies a join's or reconnect's ticket against the connection's
// game, and answers a message it refuses itself. A harness with no socket routes its clients'
// messages through one.
type Router struct {
	session *session.Manager
	secret  string
	log     *slog.Logger
	stats   *socketStats
}

// NewRouter returns a Router into manager that verifies tickets with ticketSecret and logs to
// logger.
func NewRouter(manager *session.Manager, ticketSecret string, logger *slog.Logger) *Router {
	return newRouter(manager, ticketSecret, logger, &socketStats{})
}

func newRouter(manager *session.Manager, ticketSecret string, logger *slog.Logger, stats *socketStats) *Router {
	return &Router{session: manager, secret: ticketSecret, log: logger, stats: stats}
}

// Route parses m, a message conn's client sent, and hands it to the session.
func (r *Router) Route(conn session.Connection, m wire.Map) {
	message, err := messaging.ParseClientMessage(m)
	if err != nil {
		r.stats.malformed.Add(1)
		r.connLog(conn).Warn(logInvalidMessage, "error_type", invalidMessageType(err))
		sendMessage(r.connLog(conn), conn, messaging.SessionError(
			messaging.SessionInvalidMessage, invalidMessageReason, play.Option[int]{},
		))
		return
	}

	switch msg := message.(type) {
	case messaging.GameActionMessage:
		r.session.Act(conn, msg)
	case messaging.JoinGameMessage:
		if r.verifiedTicket(conn, msg.Ticket) {
			r.session.Join(conn, msg.Ticket)
		}
	case messaging.ReconnectMessage:
		if r.verifiedTicket(conn, msg.Ticket) {
			r.session.Reconnect(conn, msg.Ticket)
		}
	case messaging.ResyncMessage:
		r.session.Resync(conn)
	}
}

func (r *Router) connLog(conn session.Connection) *slog.Logger {
	if c, ok := conn.(*connection); ok {
		return c.log
	}
	return r.log.With("game_id", conn.GameID(), "connection_id", conn.ID())
}

func invalidMessageType(err error) string {
	if invalid, ok := errors.AsType[messaging.InvalidMessageError](err); ok {
		return invalid.Reason
	}
	return "unknown"
}

func (r *Router) verifiedTicket(conn session.Connection, token string) bool {
	ticket, err := auth.VerifyTicket(token, r.secret, time.Now())
	switch {
	case err != nil:
		r.connLog(conn).Warn(logInvalidTicket, "error", err)
		r.sendTicketError(conn, "Invalid game ticket")
		return false
	case ticket.RoomID != conn.GameID():
		r.connLog(conn).Warn(logTicketMismatch, "ticket_room_id", ticket.RoomID, "expected_game_id", conn.GameID())
		r.sendTicketError(conn, "Ticket game_id mismatch")
		return false
	}
	return true
}

func (r *Router) sendTicketError(conn session.Connection, message string) {
	sendMessage(r.connLog(conn), conn, messaging.SessionError(messaging.SessionInvalidTicket, message, play.Option[int]{}))
}

func sendMessage(log *slog.Logger, conn session.Connection, m wire.Map) {
	data, err := wire.Encode(m)
	if err != nil {
		log.Error(logEncodeFailed, "error", err)
		return
	}
	conn.Send(data)
}
