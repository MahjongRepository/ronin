package main

import (
	"context"
	"flag"
	"io"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/migrate"
)

const (
	exitFailed = 1
	exitUsage  = 2
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	code := run(ctx, os.Args[1:], os.Getenv, os.Stdout, os.Stderr)
	stop()
	os.Exit(code)
}

func run(ctx context.Context, args []string, getenv func(string) string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("migrate", flag.ContinueOnError)
	flags.SetOutput(stderr)
	dir := flags.String("replay-dir", getenv("GAME_REPLAY_DIR"), "directory of the stored replays")
	database := flags.String("database", getenv("AUTH_DATABASE_PATH"), "SQLite database shared with the lobby")
	dryRun := flags.Bool("dry-run", false, "report what a run would do and write nothing")
	err := flags.Parse(args)
	if err != nil {
		return exitUsage
	}
	if *dir == "" || *database == "" || flags.NArg() > 0 {
		_, _ = io.WriteString(stderr, "migrate needs a replay directory (GAME_REPLAY_DIR or -replay-dir) "+
			"and a database (AUTH_DATABASE_PATH or -database), and takes no arguments\n")
		return exitUsage
	}

	logger := slog.New(slog.NewTextHandler(stderr, nil))
	cfg := migrate.Config{ReplayDir: *dir, DatabasePath: *database, Apply: !*dryRun}
	ok, err := migrate.Run(ctx, cfg, logger, stdout)
	if err != nil {
		logger.Error("migration did not complete", "error", err)
		return exitFailed
	}
	if !ok {
		return exitFailed
	}
	return 0
}
