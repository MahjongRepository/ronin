package migrate

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

type Config struct {
	ReplayDir    string
	DatabasePath string
	Apply        bool
}

func Run(ctx context.Context, cfg Config, logger *slog.Logger, out io.Writer) (ok bool, err error) {
	err = errors.Join(checkDir(cfg.ReplayDir), checkFile(cfg.DatabasePath))
	if err != nil {
		return false, err
	}

	replays, err := migrateReplays(ctx, cfg.ReplayDir, cfg.Apply)
	if err != nil {
		return false, err
	}

	db, err := store.Open(ctx, cfg.DatabasePath, logger)
	if err != nil {
		return false, err
	}
	defer func() { err = errors.Join(err, db.Close()) }()

	scores, err := db.MigrateFinalScores(ctx, cfg.Apply)
	if err != nil {
		return false, err
	}

	_, err = io.WriteString(out, report(cfg, replays, scores))
	if err != nil {
		return false, fmt.Errorf("write the report: %w", err)
	}

	return len(replays.Failed) == 0 && len(scores.Failed) == 0, nil
}

func checkDir(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}

	if !info.IsDir() {
		return fmt.Errorf("%s is no directory", path)
	}

	return nil
}

func checkFile(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}

	if info.IsDir() {
		return fmt.Errorf("%s is a directory", path)
	}

	return nil
}

func report(cfg Config, replays replayReport, scores store.ScoreMigration) string {
	var b strings.Builder
	fmt.Fprintf(&b, "replays in %s: %d rewritten, %d already current, %d failed, %d ignored\n",
		cfg.ReplayDir, replays.Rewritten, replays.Current, len(replays.Failed), len(replays.Ignored))
	for t, n := range replays.Transforms {
		fmt.Fprintf(&b, "  %s: %d\n", Transform(t), n)
	}

	fmt.Fprintf(&b, "  without a game end: %d, of them cut inside a record: %d\n", replays.Unfinished, replays.Cut)
	for kind, n := range replays.Kinds() {
		if n > 0 {
			fmt.Fprintf(&b, "  failed as %s: %d\n", FailureKind(kind), n)
		}
	}

	for _, f := range replays.Failed {
		fmt.Fprintf(&b, "  failed %s\n", f.Error())
	}

	for _, name := range replays.Ignored {
		fmt.Fprintf(&b, "  ignored %s\n", name)
	}

	fmt.Fprintf(&b, "played games in %s: %d converted to tenths, %d already in tenths, %d without final scores, %d failed\n",
		cfg.DatabasePath, scores.Converted, scores.AlreadyTenths, scores.Unscored, len(scores.Failed))
	for _, f := range scores.Failed {
		fmt.Fprintf(&b, "  failed %s\n", f.Error())
	}

	if cfg.Apply {
		b.WriteString("written\n")
	} else {
		b.WriteString("dry run: nothing written\n")
	}

	return b.String()
}
