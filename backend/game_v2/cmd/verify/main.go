// Command verify checks that the stored replay of each game it is given reproduces the game: the
// replay records the game end, and played again through the engine from its seed it ends every
// round and the game exactly as it recorded. It is the Go server's replay check, which
// bin/verify_games.py is to run beside its own check of the games' rows.
//
// Usage:
//
//	verify [-replay-dir dir] game_id...
//
// The replay directory defaults to GAME_REPLAY_DIR, the game server's. It prints one line per game,
// "ok" or "FAILED" with the reason, then how many passed, and exits 1 when a game fails or none is
// given, 2 on a usage error.
package main

import (
	"flag"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
)

const (
	exitFailed = 1
	exitUsage  = 2
)

func main() {
	os.Exit(run(os.Args[1:], os.Getenv, os.Stdout, os.Stderr))
}

func run(args []string, getenv func(string) string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("verify", flag.ContinueOnError)
	flags.SetOutput(stderr)
	dir := flags.String("replay-dir", getenv("GAME_REPLAY_DIR"), "directory of the stored replays")
	err := flags.Parse(args)
	if err != nil {
		return exitUsage
	}
	if *dir == "" {
		return report(stderr, "no replay directory: set GAME_REPLAY_DIR or pass -replay-dir\n", exitUsage)
	}

	ids := flags.Args()
	if len(ids) == 0 {
		return report(stdout, "no game ids to verify\n", exitFailed)
	}

	replays := replayfile.New(*dir)
	var lines strings.Builder
	failures := 0
	for _, id := range ids {
		problem := verifyGame(replays, id)
		if problem == nil {
			lines.WriteString("ok      " + id + "\n")
			continue
		}

		failures++
		lines.WriteString("FAILED  " + id + ": " + problem.Error() + "\n")
	}
	lines.WriteString(strconv.Itoa(len(ids)-failures) + "/" + strconv.Itoa(len(ids)) + " game(s) verified\n")

	if failures > 0 {
		return report(stdout, lines.String(), exitFailed)
	}
	return report(stdout, lines.String(), 0)
}

func report(w io.Writer, text string, code int) int {
	_, err := io.WriteString(w, text)
	if err != nil {
		return exitFailed
	}
	return code
}
