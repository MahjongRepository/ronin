// Command fixtures generates the fixtures the game client's tests and storybook read: the seat
// transcripts, by playing the seat scenarios through the real session manager, message router and
// engine on virtual time (what each named seat's client received, the game actions it sent, and
// the sockets it opened and saw close); and the replay files, by playing the replay scenarios
// through the engine and recording them as the session does (games dealt from a staged wall and
// played seat by seat, games dealt from their seed and played by a fixed policy, and cuts of
// those), each reproducing its game through the replay runner before it is written.
//
// Usage:
//
//	fixtures [-check] [-seat-scenarios dir] [-replays dir]
//
// The directories default to the game client's seat scenarios and replay fixtures, relative to
// backend/game_v2. It writes every fixture and removes the ones no scenario produces; with -check
// nothing is written, and it exits 1 naming each fixture that differs from what the server and the
// engine produce now, is missing, or has no scenario. It exits 2 on a usage error, and 1 when a
// scenario fails.
//
// Ported from ronin's Python seat scenario and replay fixture generators and their harnesses.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
)

const (
	exitFailed = 1
	exitUsage  = 2
)

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdout, os.Stderr))
}

type fixtureSet struct {
	kind string
	dir  fixtureDir
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("fixtures", flag.ContinueOnError)
	flags.SetOutput(stderr)
	check := flags.Bool("check", false, "fail on drift instead of writing the fixtures")
	seatDir := flags.String("seat-scenarios", "../../frontend/game_v2/src/fixtures/seat-scenarios",
		"directory of the seat transcripts")
	replayDir := flags.String("replays", "../../frontend/game_v2/src/fixtures/replays",
		"directory of the replay fixtures")
	if flags.Parse(args) != nil || flags.NArg() > 0 {
		return exitUsage
	}

	logger := slog.New(slog.NewTextHandler(stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	transcripts, err := generateSeatTranscripts(ctx, logger)
	if err != nil {
		return report(stderr, "seat scenario failed: "+err.Error()+"\n", exitFailed)
	}
	replays, err := generateReplayFixtures()
	if err != nil {
		return report(stderr, "replay scenario failed: "+err.Error()+"\n", exitFailed)
	}

	sets := []fixtureSet{
		{kind: "seat transcript", dir: fixtureDir{path: *seatDir, suffix: ".json"}},
		{kind: "replay fixture", dir: fixtureDir{path: *replayDir, suffix: ".msgpack"}},
	}
	generated := []map[string][]byte{transcripts, replays}
	code := 0
	for i, set := range sets {
		if *check {
			code = max(code, checkFixtures(set, generated[i], stdout, stderr))
		} else {
			code = max(code, writeFixtures(set, generated[i], stdout, stderr))
		}
	}
	return code
}

func checkFixtures(set fixtureSet, generated map[string][]byte, stdout, stderr io.Writer) int {
	problems, err := set.dir.drift(generated)
	if err != nil {
		return report(stderr, "read the "+set.kind+"s: "+err.Error()+"\n", exitFailed)
	}
	if len(problems) == 0 {
		return report(stdout, fmt.Sprintf("%d %s(s) up to date\n", len(generated), set.kind), 0)
	}

	var lines strings.Builder
	for _, problem := range problems {
		lines.WriteString(problem + "\n")
	}
	lines.WriteString(set.kind + "s drifted: regenerate them and update the client\n")
	return report(stdout, lines.String(), exitFailed)
}

func writeFixtures(set fixtureSet, generated map[string][]byte, stdout, stderr io.Writer) int {
	removed, err := set.dir.write(generated)
	var lines strings.Builder
	for _, name := range removed {
		lines.WriteString("removed " + name + "\n")
	}
	if err != nil {
		return report(stderr, lines.String()+"write the "+set.kind+"s: "+err.Error()+"\n", exitFailed)
	}
	fmt.Fprintf(&lines, "wrote %d %s(s) to %s\n", len(generated), set.kind, set.dir.path)
	return report(stdout, lines.String(), 0)
}

func report(w io.Writer, text string, code int) int {
	_, err := io.WriteString(w, text)
	if err != nil {
		return exitFailed
	}
	return code
}
