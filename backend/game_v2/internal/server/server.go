package server

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
)

type SocketConfig struct {
	PingInterval    time.Duration
	PingTimeout     time.Duration
	SendDeadline    time.Duration
	Rate            float64
	Burst           int
	ResyncRate      float64
	ResyncBurst     int
	MaxDecodeErrors int
}

func DefaultSocketConfig() SocketConfig {
	return SocketConfig{
		PingInterval:    20 * time.Second,
		PingTimeout:     20 * time.Second,
		SendDeadline:    10 * time.Second,
		Rate:            50,
		Burst:           80,
		ResyncRate:      0.2,
		ResyncBurst:     2,
		MaxDecodeErrors: 5,
	}
}

type Config struct {
	Session        *session.Manager
	Replays        replayfile.Dir
	TicketSecret   string
	InternalSecret string
	CORSOrigins    []string
	Version        string
	Commit         string
	Logger         *slog.Logger
	Socket         SocketConfig
	Now            func() time.Time
}

var ErrConfig = errors.New("invalid server config")

func (c Config) valid() bool {
	k := c.Socket
	switch {
	case c.Session == nil || c.Logger == nil || c.TicketSecret == "" || c.InternalSecret == "":
		return false
	case k.PingInterval <= 0 || k.PingTimeout <= 0 || k.SendDeadline <= 0:
		return false
	case k.Rate < 0 || k.ResyncRate < 0 || k.Burst <= 0 || k.ResyncBurst <= 0 || k.MaxDecodeErrors <= 0:
		return false
	}

	return true
}

// Server serves the game server's routes and tracks every socket it accepted, so Shutdown can
// close them.
type Server struct {
	cfg       Config
	log       *slog.Logger
	startedAt int64
	stats     socketStats
	router    *Router
	handler   http.Handler

	mu      sync.Mutex
	closing bool
	sockets map[*connection]struct{}
	served  sync.WaitGroup
}

// New returns a Server on cfg, its process start taken as now.
func New(cfg Config) (*Server, error) {
	if !cfg.valid() {
		return nil, ErrConfig
	}

	if cfg.Now == nil {
		cfg.Now = time.Now
	}

	s := &Server{
		cfg:       cfg,
		log:       cfg.Logger,
		startedAt: cfg.Now().Unix(),
		sockets:   map[*connection]struct{}{},
	}
	s.stats.closes = initialCloses()
	s.router = newRouter(cfg.Session, cfg.TicketSecret, cfg.Logger, &s.stats, cfg.Now)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.health)
	mux.HandleFunc("GET /status", s.status)
	mux.HandleFunc("POST /games", s.createGame)
	mux.HandleFunc("GET /games", s.playingGames)
	mux.HandleFunc("GET /games/{game_id}/observe", s.observeGame)
	mux.HandleFunc("DELETE /games/{game_id}", s.withdrawGame)
	mux.HandleFunc("GET /players/{user_id}", s.playerGame)
	mux.HandleFunc("GET /players/{user_id}/game-session", s.playerGameSession)
	mux.HandleFunc("GET /replays/{game_id}/tenhou", s.tenhouReplay)
	mux.HandleFunc("GET /ws/{game_id}", s.serveSocket)
	s.handler = newCORS(cfg.CORSOrigins, mux)
	return s, nil
}

// Handler returns the handler serving every route.
func (s *Server) Handler() http.Handler {
	return s.handler
}

func (s *Server) Shutdown(ctx context.Context) error {
	for _, conn := range s.stopServing() {
		conn.closeForShutdown()
	}

	drained := make(chan struct{})
	go func() {
		s.served.Wait()
		close(drained)
	}()

	var socketsErr error
	select {
	case <-drained:
	case <-ctx.Done():
		socketsErr = ctx.Err()
		var terminating sync.WaitGroup
		for _, conn := range s.openSockets() {
			terminating.Go(conn.terminate)
		}

		terminating.Wait()
	}

	return errors.Join(socketsErr, s.cfg.Session.Shutdown(ctx))
}

func (s *Server) stopServing() []*connection {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.closing = true
	return s.openSocketsLocked()
}

func (s *Server) openSockets() []*connection {
	s.mu.Lock()
	defer s.mu.Unlock()

	return s.openSocketsLocked()
}

func (s *Server) openSocketsLocked() []*connection {
	conns := make([]*connection, 0, len(s.sockets))
	for conn := range s.sockets {
		conns = append(conns, conn)
	}

	return conns
}

func (s *Server) track(conn *connection) bool {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closing {
		return false
	}

	s.sockets[conn] = struct{}{}
	s.served.Add(1)
	return true
}

func (s *Server) untrack(conn *connection) {
	s.mu.Lock()
	defer s.mu.Unlock()

	delete(s.sockets, conn)
	s.served.Done()
}
