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
