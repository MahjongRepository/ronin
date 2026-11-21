package migrate

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type replayReport struct {
	Rewritten  int
	Transforms [transformCount]int
	Unfinished int
	Cut        int
	Current    int
	Ignored    []string
	Failed     []replayFailure
}

type replayFailure struct {
	GameID string
	Err    error
}

func (f replayFailure) Error() string {
	return "replay " + f.GameID + ": " + f.Err.Error()
}

// Kinds counts the failures by FailureKind.
func (r replayReport) Kinds() [failureKindCount]int {
	var kinds [failureKindCount]int
	for _, f := range r.Failed {
		if rewriteErr, ok := errors.AsType[RewriteError](f.Err); ok {
			kinds[rewriteErr.Kind]++
		}
	}
	return kinds
}

func migrateReplays(ctx context.Context, dir string, apply bool) (report replayReport, err error) {
	root, err := os.OpenRoot(dir)
	if err != nil {
		return replayReport{}, fmt.Errorf("open replay directory: %w", err)
	}
	defer func() { err = errors.Join(err, root.Close()) }()

	replays := replayfile.New(dir)
	err = fs.WalkDir(root.FS(), ".", func(name string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if entry.IsDir() {
			return nil
		}

		gameID, ok := storedGameID(name, entry)
		if !ok {
			report.Ignored = append(report.Ignored, name)
			return nil
		}
		report.add(gameID, migrateReplay(replays, gameID, apply))
		return nil
	})
	if err != nil {
		return replayReport{}, fmt.Errorf("walk replay directory: %w", err)
	}
	return report, nil
}

type replayOutcome struct {
	rewritten Rewritten
	current   bool
	err       error
}

func (r *replayReport) add(gameID string, outcome replayOutcome) {
	switch {
	case outcome.err != nil:
		r.Failed = append(r.Failed, replayFailure{GameID: gameID, Err: outcome.err})
	case outcome.current:
		r.Current++
	default:
		r.Rewritten++
		for _, t := range outcome.rewritten.Transforms {
			r.Transforms[t]++
		}
		if !outcome.rewritten.GameEnded {
			r.Unfinished++
		}
		if outcome.rewritten.Cut {
			r.Cut++
		}
	}
}

func storedGameID(name string, entry fs.DirEntry) (string, bool) {
	gameID, isReplay := strings.CutSuffix(path.Base(name), replayfile.Suffix)
	if !isReplay || !entry.Type().IsRegular() || !replayfile.IsValidGameID(gameID) {
		return "", false
	}
	return gameID, name == replayfile.Path(gameID)
}

func migrateReplay(replays replayfile.Dir, gameID string, apply bool) replayOutcome {
	compressed, err := replays.Read(gameID)
	if err != nil {
		return replayOutcome{err: RewriteError{Kind: FailureUnreadable, Err: err}}
	}
	content, err := replayfile.Decompress(compressed, wire.MaxReplayBytes)
	if err != nil {
		return replayOutcome{err: RewriteError{Kind: FailureUnreadable, Err: err}}
	}

	_, err = wire.DecodeReplay(content)
	if err == nil {
		return replayOutcome{current: true}
	}
	if _, isOtherVersion := errors.AsType[wire.UnsupportedVersionError](err); !isOtherVersion {
		return replayOutcome{err: RewriteError{Kind: FailureUnreadable, Err: err}}
	}

	rewritten, err := Rewrite(content)
	if err != nil {
		return replayOutcome{err: err}
	}
	if apply {
		err = replays.Save(gameID, rewritten.Content)
		if err != nil {
			return replayOutcome{err: RewriteError{Kind: FailureWrite, Err: err}}
		}
	}
	return replayOutcome{rewritten: rewritten}
}
