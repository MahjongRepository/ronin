// Package server is the game server's transport: the lobby's REST routes, /health and /status,
// and the WebSocket endpoint each client plays its game over.
//
// The server owns every socket: one goroutine reads it and hands each decoded, rate-limited
// message to the session, one writes its queued sends in order, and one pings it. The session sees
// a socket only as a session.Connection whose sends and close never wait on the client. A graceful
// stop closes every socket with 1012 so each runs its disconnect, and only then shuts the session
// down, so a game ends through its players' disconnects and its finalizer still runs.
//
// Ported from ronin's Python game server: its app, WebSocket endpoint, message router, socket
// counters and settings, and the shared queued WebSocket and token bucket.
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

// SocketConfig is how the server serves each socket: its liveness ping and how long a pong may
// take, how long one send may block before the socket is dropped, the message budget every frame
// draws on (a rate per second over a burst), the far tighter budget of resync requests, and how
// many undecodable frames in a row close the socket.
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

// DefaultSocketConfig returns the production socket settings: a ping every 20 s answered within
// 20 s, a 10 s send deadline, 50 messages a second over a burst of 80, a resync every 5 s over a
// burst of 2, and 5 undecodable frames in a row.
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

// Config is what a Server runs on. Session and Logger are required, and so are both secrets.
// Replays is where the Tenhou export reads the stored replays; CORSOrigins are the origins whose
// scripts may read the REST answers ("*" for any); Version and Commit are what /health and /status
// report; Now is where the server reads the time its tickets, rate limits and process start are
// taken at, time.Now when nil.
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

// ErrConfig is returned by New for a Config it cannot run on.
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

// Shutdown stops the server once its HTTP server stopped taking connections: it refuses new
// sockets, closes every open one with 1012 and waits until each ran its disconnect, and then shuts
// the session down, which waits for the finalizers and store writes. When ctx ends first, the
// sockets still open are dropped and the session is cut short.
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
