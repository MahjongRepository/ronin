package server

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"net/http"
	"strconv"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/auth"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	maxRequestBody        = 4096
	createBodyReadTimeout = 10 * time.Second
	logWriteFailed        = "write response"
	logCreateFailed       = "create game failed"
	logReplayUnread       = "read stored replay failed"
	logTenhouFailed       = "tenhou export failed"
	statusOK              = "ok"
	statusPending         = "pending"
	cacheControlNone      = "no-store"
)

type errorBody struct {
	Error string `json:"error"`
}

func (s *Server) writeJSON(w http.ResponseWriter, status int, body any) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	err := enc.Encode(body)
	if err != nil {
		s.log.Error(logWriteFailed, "error", err)
		http.Error(w, "", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, err = w.Write(bytes.TrimSuffix(buf.Bytes(), []byte("\n")))
	if err != nil {
		s.log.Debug(logWriteFailed, "error", err)
	}
}

func (s *Server) writeError(w http.ResponseWriter, status int, message string) {
	s.writeJSON(w, status, errorBody{Error: message})
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	s.writeJSON(w, http.StatusOK, struct {
		Status  string `json:"status"`
		Version string `json:"version"`
		Commit  string `json:"commit"`
	}{statusOK, s.cfg.Version, s.cfg.Commit})
}

type statusField struct {
	name  string
	value any
}

func (s *Server) status(w http.ResponseWriter, _ *http.Request) {
	counts := s.cfg.Session.GameCounts()
	stats := s.cfg.Session.Stats()
	lag, measured := s.cfg.Session.QueueDelayMax()
	var lagValue any
	if measured {
		lagValue = lag
	}

	fields := []statusField{
		{"status", statusOK},
		{"version", s.cfg.Version},
		{"commit", s.cfg.Commit},
		{"pending_games", counts.Pending},
		{"active_games", counts.Playing},
		{"capacity_used", counts.Pending + counts.Playing},
		{"max_capacity", s.cfg.Session.Capacity()},
		{"started_at", s.startedAt},
		{"reconnects", stats.Reconnects},
		{"takeovers", stats.Takeovers},
		{"resyncs", stats.Resyncs},
		{"timeouts_turn", stats.TurnTimeouts},
		{"timeouts_meld", stats.MeldTimeouts},
		{"timeouts_round_advance", stats.RoundAdvanceTimeouts},
		{"ai_replacements", stats.AIReplacements},
		{"connections", s.stats.connections.Load()},
		{"connections_accepted", s.stats.accepted.Load()},
		{"messages_in", s.stats.messagesIn.Load()},
		{"bytes_in", s.stats.bytesIn.Load()},
		{"messages_out", s.stats.messagesOut.Load()},
		{"bytes_out", s.stats.bytesOut.Load()},
		{"handling_seconds", time.Duration(s.stats.handlingNanos.Load()).Seconds()},
		{"handled_messages", s.stats.handled.Load()},
		{"malformed_messages", s.stats.malformed.Load()},
		{"rate_limited_messages", s.stats.rateLimited.Load()},
	}
	for _, c := range s.stats.closeCounts() {
		fields = append(fields, statusField{"closes_" + strconv.Itoa(c.code), c.count})
	}
	fields = append(fields, statusField{"loop_lag_max_ms", lagValue})
	s.writeJSON(w, http.StatusOK, orderedObject(fields))
}

type orderedObject []statusField

func (o orderedObject) MarshalJSON() ([]byte, error) {
	buf := []byte{'{'}
	for i, f := range o {
		if i > 0 {
			buf = append(buf, ',')
		}
		buf = strconv.AppendQuote(buf, f.name)
		buf = append(buf, ':')
		value, err := json.Marshal(f.value)
		if err != nil {
			return nil, err
		}
		buf = append(buf, value...)
	}
	return append(buf, '}'), nil
}

func (s *Server) isInternalCaller(r *http.Request) bool {
	return auth.IsInternalBearer(r.Header.Get("Authorization"), s.cfg.InternalSecret)
}

func (s *Server) playerGame(w http.ResponseWriter, r *http.Request) {
	playing, ok := s.cfg.Session.PlayingGame(r.PathValue("user_id"))
	if !ok {
		s.writeError(w, http.StatusNotFound, "Player is not in a game")
		return
	}
	s.writeJSON(w, http.StatusOK, struct {
		GameID string `json:"game_id"`
	}{playing.GameID})
}

func (s *Server) playerGameSession(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", cacheControlNone)
	if !s.isInternalCaller(r) {
		s.writeError(w, http.StatusUnauthorized, "Unauthorized")
		return
	}

	playing, ok := s.cfg.Session.PlayingGame(r.PathValue("user_id"))
	if !ok {
		s.writeError(w, http.StatusNotFound, "Player is not in a game")
		return
	}
	s.writeJSON(w, http.StatusOK, struct {
		GameID string `json:"game_id"`
		Ticket string `json:"game_ticket"`
	}{playing.GameID, playing.Ticket})
}

func (s *Server) withdrawGame(w http.ResponseWriter, r *http.Request) {
	if !s.isInternalCaller(r) {
		s.writeError(w, http.StatusUnauthorized, "Unauthorized")
		return
	}
	gameID := r.PathValue("game_id")
	if !store.IsValidGameID(gameID) {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if !s.cfg.Session.WithdrawGame(gameID) {
		s.writeError(w, http.StatusConflict, "Game already joined")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) tenhouReplay(w http.ResponseWriter, r *http.Request) {
	if !s.isInternalCaller(r) {
		s.writeError(w, http.StatusUnauthorized, "Unauthorized")
		return
	}

	gameID := r.PathValue("game_id")
	compressed, err := s.cfg.Replays.Read(gameID)
	if err != nil {
		if !errors.Is(err, store.ErrInvalidGameID) && !errors.Is(err, fs.ErrNotExist) {
			s.log.Warn(logReplayUnread, "game_id", gameID, "error", err)
		}
		s.writeError(w, http.StatusNotFound, "Replay not found")
		return
	}

	xml, err := exportTenhou(compressed)
	if errors.Is(err, tenhou.ErrNoGameEnd) {
		s.writeError(w, http.StatusUnprocessableEntity, "Replay has no game end")
		return
	}
	if err != nil {
		s.log.Error(logTenhouFailed, "game_id", gameID, "error", err)
		s.writeError(w, http.StatusInternalServerError, "Internal server error")
		return
	}

	w.Header().Set("Content-Type", "application/xml")
	w.WriteHeader(http.StatusOK)
	_, err = io.WriteString(w, xml)
	if err != nil {
		s.log.Debug(logWriteFailed, "error", err)
	}
}

func exportTenhou(compressed []byte) (string, error) {
	content, err := store.DecompressReplay(compressed, wire.MaxReplayBytes)
	if err != nil {
		return "", err
	}
	return tenhou.Convert(content)
}

func (s *Server) createGame(w http.ResponseWriter, r *http.Request) {
	err := http.NewResponseController(w).SetReadDeadline(time.Now().Add(createBodyReadTimeout))
	if err != nil {
		s.log.Error(logCreateFailed, "error", err)
		s.writeError(w, http.StatusInternalServerError, "Internal server error")
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxRequestBody))
	if err != nil {
		if _, tooLarge := errors.AsType[*http.MaxBytesError](err); tooLarge {
			s.writeError(w, http.StatusRequestEntityTooLarge, "Request body too large")
			return
		}
		s.writeError(w, http.StatusBadRequest, "Client disconnected")
		return
	}

	request, ok := parseCreateGame(body)
	if !ok {
		s.writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}
	if ticketError := s.ticketError(request); ticketError != "" {
		s.writeError(w, http.StatusBadRequest, ticketError)
		return
	}

	err = s.cfg.Session.CreatePendingGame(request.gameID, request.players)
	if err != nil {
		status, message := creationRefusal(err)
		if status == http.StatusInternalServerError {
			s.log.Error(logCreateFailed, "game_id", request.gameID, "error", err)
		}
		s.writeError(w, status, message)
		return
	}
	s.writeJSON(w, http.StatusCreated, struct {
		GameID string `json:"game_id"`
		Status string `json:"status"`
	}{request.gameID, statusPending})
}

func (s *Server) ticketError(request createGameRequest) string {
	now := s.cfg.Now()
	for _, player := range request.players {
		ticket, err := auth.VerifyTicket(player.Ticket, s.cfg.TicketSecret, now)
		switch {
		case err != nil:
			return "Invalid or expired game ticket"
		case ticket.RoomID != request.gameID:
			return "Ticket game_id mismatch"
		case ticket.Username != player.Name || ticket.UserID != player.UserID:
			return "Ticket identity mismatch"
		}
	}
	return ""
}

func creationRefusal(err error) (int, string) {
	switch {
	case errors.Is(err, session.ErrPlayerPlaying):
		return http.StatusConflict, "Player already in a game"
	case errors.Is(err, session.ErrAtCapacity):
		return http.StatusServiceUnavailable, "Server at capacity"
	case errors.Is(err, session.ErrShuttingDown):
		return http.StatusServiceUnavailable, "Server is shutting down"
	case errors.Is(err, session.ErrGameExists), errors.Is(err, session.ErrGameWithdrawn):
		return http.StatusConflict, "Game with this ID already exists"
	case errors.Is(err, session.ErrPlayerCount):
		return http.StatusBadRequest, "Invalid request body"
	}
	return http.StatusInternalServerError, "Internal server error"
}
