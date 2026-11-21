// Package migrate moves the data the Python game server left into the Go server's formats, once:
// every stored replay of version 0.4-dev rewritten into the current replay version, and the final
// scores of every `played_games` row from whole points into tenths. cmd/migrate runs it, and
// nothing else calls it.
//
// A rewritten replay shows the game as it was played and scored under the old rules, so it keeps
// rules profile wire.MigratedRulesProfileID and does not reproduce under the engine. Each change is
// derived from what the old file holds, and a replay the rewrite cannot carry over whole is left as
// it was and reported. Both halves are idempotent: a replay at the current version and a row marked
// in tenths are never touched again.
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

// Config is what Run migrates: the replay directory and the SQLite database the game server
// shares with the lobby, both of which must exist, and whether to write the changes or only report
// them.
type Config struct {
	ReplayDir    string
	DatabasePath string
	Apply        bool
}

// Run migrates the replays and then the final scores cfg names, and writes its report to out:
// counts per transform and per failure, each failure and each ignored path. It returns whether
// nothing failed; the error is for a run that could not complete, one matching fs.ErrNotExist for a
// missing input, which Run never creates. The logger takes the store's warnings.
func Run(ctx context.Context, cfg Config, logger *slog.Logger, out io.Writer) (ok bool, err error) {
	err = errors.Join(checkExists(cfg.ReplayDir, true), checkExists(cfg.DatabasePath, false))
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

func checkExists(path string, dir bool) error {
	info, err := os.Stat(path)
	switch {
	case err != nil:
		return err
	case dir && !info.IsDir():
		return fmt.Errorf("%s is no directory", path)
	case !dir && info.IsDir():
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
