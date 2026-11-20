// Command gameserver runs the Go game server: it reads its environment, opens the shared database
// and the replay store, and serves the lobby's routes and the game sockets until SIGINT or SIGTERM,
// then stops within the container's grace period: the HTTP server stops taking connections, every
// socket closes as a disconnect, the games' finalizers drain, and the database closes last. With
// -cpuprofile it writes a CPU profile of the whole run there, for make profile-games.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/server"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

const (
	readHeaderTimeout = 10 * time.Second
	idleTimeout       = 5 * time.Second
	shutdownTimeout   = 14 * time.Second
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8712", "address to listen on")
	cpuProfile := flag.String("cpuprofile", "", "write a CPU profile of the whole run to this file")
	flag.Parse()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	err := runProfiled(ctx, *addr, *cpuProfile)
	stop()

	if err == nil {
		return
	}
	if _, logged := errors.AsType[loggedError](err); !logged {
		slog.Error(logStopped, "error", err)
	}
	os.Exit(1)
}

const logStopped = "game server stopped"

type loggedError struct {
	error
}

func run(ctx context.Context, addr string) (err error) {
	cfg, err := loadConfig(os.Getenv)
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}
	logger, closeLog, err := newLogger(cfg)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeLog()) }()

	err = runLogged(ctx, addr, cfg, logger)
	if err != nil {
		logger.Error(logStopped, "error", err)
		return loggedError{err}
	}
	return nil
}

func runLogged(ctx context.Context, addr string, cfg config, logger *slog.Logger) (err error) {
	storeCtx, cancelStore := context.WithCancel(context.WithoutCancel(ctx))
	defer cancelStore()
	db, err := store.Open(storeCtx, cfg.databasePath, logger)
	if err != nil {
		return fmt.Errorf("open database: %w", err)
	}
	defer func() { err = errors.Join(err, db.Close()) }()

	srv, err := newServer(storeCtx, cfg, db, logger)
	if err != nil {
		return err
	}
	return serve(ctx, addr, srv, logger, cancelStore)
}

func newLogger(cfg config) (*slog.Logger, func() error, error) {
	var out io.Writer = os.Stdout
	closeLog := func() error { return nil }
	if cfg.logDir != "" {
		file, err := openWatchedFile(cfg.logDir)
		if err != nil {
			return nil, nil, err
		}
		out, closeLog = io.MultiWriter(os.Stdout, file), file.Close
	}

	options := &slog.HandlerOptions{Level: cfg.logLevel}
	if cfg.logJSON {
		return slog.New(slog.NewJSONHandler(out, options)), closeLog, nil
	}
	return slog.New(slog.NewTextHandler(out, options)), closeLog, nil
}

func newServer(storeCtx context.Context, cfg config, db *store.DB, logger *slog.Logger) (*server.Server, error) {
	replays := store.NewReplays(cfg.replayDir)
	manager, err := session.New(storeCtx, session.Config{
		Timing:   session.DefaultTiming(),
		Capacity: cfg.capacity,
		DB:       db,
		Replays:  replays,
		Logger:   logger,
	})
	if err != nil {
		return nil, fmt.Errorf("start session: %w", err)
	}

	srv, err := server.New(server.Config{
		Session:        manager,
		Replays:        replays,
		Capacity:       cfg.capacity,
		TicketSecret:   cfg.ticketSecret,
		InternalSecret: cfg.internalSecret,
		CORSOrigins:    cfg.corsOrigins,
		Version:        cfg.version,
		Commit:         cfg.commit,
		Logger:         logger,
		Socket:         server.DefaultSocketConfig(),
	})
	if err != nil {
		return nil, fmt.Errorf("start server: %w", err)
	}
	return srv, nil
}

func serve(ctx context.Context, addr string, srv *server.Server, logger *slog.Logger, cancelStore func()) error {
	listener, err := (&net.ListenConfig{}).Listen(ctx, "tcp", addr)
	if err != nil {
		return fmt.Errorf("listen on %s: %w", addr, err)
	}
	httpServer := &http.Server{
		Handler:           srv.Handler(),
		ReadHeaderTimeout: readHeaderTimeout,
		IdleTimeout:       idleTimeout,
		ErrorLog:          slog.NewLogLogger(logger.Handler(), slog.LevelError),
	}
	serveErr := make(chan error, 1)
	go func() {
		serveErr <- httpServer.Serve(listener)
	}()
	logger.Info("game server ready", "addr", addr)

	select {
	case failed := <-serveErr:
		return fmt.Errorf("serve %s: %w", addr, failed)
	case <-ctx.Done():
	}

	shutdownCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), shutdownTimeout)
	defer cancel()
	stopCutting := context.AfterFunc(shutdownCtx, cancelStore)
	defer stopCutting()

	httpErr := httpServer.Shutdown(shutdownCtx)
	shutdownErr := srv.Shutdown(shutdownCtx)
	err = <-serveErr
	if errors.Is(err, http.ErrServerClosed) {
		err = nil
	}
	return errors.Join(httpErr, shutdownErr, err)
}
