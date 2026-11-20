package migrate

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	replaySuffix = ".msgpack.gz"
	shardLength  = 2
)

// ReplayReport is what MigrateReplays found in a replay directory: the replays it rewrote, with
// how many took each Transform, how many hold no game end and how many of those ended inside a
// record; the replays already at the current version; the paths that name no stored replay; and
// the replays it left as they were.
type ReplayReport struct {
	Rewritten  int
	Transforms [transformCount]int
	Unfinished int
	Cut        int
	Current    int
	Ignored    []string
	Failed     []ReplayFailure
}

// ReplayFailure is a stored replay MigrateReplays left as it was, and why: Err is a RewriteError.
type ReplayFailure struct {
	GameID string
	Err    error
}

func (f ReplayFailure) Error() string {
	return "replay " + f.GameID + ": " + f.Err.Error()
}

// Kinds counts the failures by FailureKind.
func (r ReplayReport) Kinds() [failureKindCount]int {
	var kinds [failureKindCount]int
	for _, f := range r.Failed {
		if rewriteErr, ok := errors.AsType[RewriteError](f.Err); ok {
			kinds[rewriteErr.Kind]++
		}
	}
	return kinds
}

// MigrateReplays rewrites every replay of version 0.4-dev stored under dir, at the paths the game
// server stores them, into the current version, each through the store's own write path. A replay
// already at the current version is left as it is, so a second run rewrites nothing; so is one
// Rewrite refuses, reported among the failures. A file at any other path is ignored and listed.
// With apply false nothing is written: the report is what a run would do. The error is for a
// directory it cannot walk.
func MigrateReplays(dir string, apply bool) (report ReplayReport, err error) {
	root, err := os.OpenRoot(dir)
	if err != nil {
		return ReplayReport{}, fmt.Errorf("open replay directory: %w", err)
	}
	defer func() { err = errors.Join(err, root.Close()) }()

	replays := store.NewReplays(dir)
	err = fs.WalkDir(root.FS(), ".", func(name string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
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
		return ReplayReport{}, fmt.Errorf("walk replay directory: %w", err)
	}
	return report, nil
}

type replayOutcome struct {
	rewritten Rewritten
	current   bool
	err       error
}

func (r *ReplayReport) add(gameID string, outcome replayOutcome) {
	switch {
	case outcome.err != nil:
		r.Failed = append(r.Failed, ReplayFailure{GameID: gameID, Err: outcome.err})
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
	gameID, isReplay := strings.CutSuffix(path.Base(name), replaySuffix)
	if !isReplay || !entry.Type().IsRegular() || !store.IsValidGameID(gameID) {
		return "", false
	}
	return gameID, name == path.Join(gameID[:shardLength], gameID[shardLength:2*shardLength], gameID+replaySuffix)
}

func migrateReplay(replays store.Replays, gameID string, apply bool) replayOutcome {
	compressed, err := replays.Read(gameID)
	if err != nil {
		return replayOutcome{err: RewriteError{Kind: FailureUnreadable, Err: err}}
	}
	content, err := store.DecompressReplay(compressed, wire.MaxReplayBytes)
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
