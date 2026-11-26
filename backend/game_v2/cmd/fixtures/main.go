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
	kind      string
	dir       fixtureDir
	generated map[string][]byte
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
		{kind: "seat transcript", dir: fixtureDir{path: *seatDir, suffix: ".json"}, generated: transcripts},
		{kind: "replay fixture", dir: fixtureDir{path: *replayDir, suffix: ".msgpack"}, generated: replays},
	}
	code := 0
	for _, set := range sets {
		if *check {
			code = max(code, checkFixtures(set, stdout, stderr))
		} else {
			code = max(code, writeFixtures(set, stdout, stderr))
		}
	}

	return code
}

func checkFixtures(set fixtureSet, stdout, stderr io.Writer) int {
	problems, err := set.dir.drift(set.generated)
	if err != nil {
		return report(stderr, "read the "+set.kind+"s: "+err.Error()+"\n", exitFailed)
	}

	if len(problems) == 0 {
		return report(stdout, fmt.Sprintf("%d %s(s) up to date\n", len(set.generated), set.kind), 0)
	}

	var lines strings.Builder
	for _, problem := range problems {
		lines.WriteString(problem + "\n")
	}

	lines.WriteString(set.kind + "s drifted: regenerate them and update the client\n")
	return report(stdout, lines.String(), exitFailed)
}

func writeFixtures(set fixtureSet, stdout, stderr io.Writer) int {
	removed, err := set.dir.write(set.generated)
	if err != nil {
		return report(stderr, removalLines(removed)+"write the "+set.kind+"s: "+err.Error()+"\n", exitFailed)
	}

	wrote := fmt.Sprintf("wrote %d %s(s) to %s\n", len(set.generated), set.kind, set.dir.path)
	return report(stdout, removalLines(removed)+wrote, 0)
}

func removalLines(removed []string) string {
	var lines strings.Builder
	for _, name := range removed {
		lines.WriteString("removed " + name + "\n")
	}

	return lines.String()
}

func report(w io.Writer, text string, code int) int {
	_, err := io.WriteString(w, text)
	if err != nil {
		return exitFailed
	}

	return code
}
