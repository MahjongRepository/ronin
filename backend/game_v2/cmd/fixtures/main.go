// Command fixtures generates the seat transcripts the game client's scenario tests and storybook
// read, by playing the seat scenarios through the real session manager, message router and engine
// on virtual time: what each named seat's client received, the game actions it sent, and the
// sockets it opened and saw close.
//
// Usage:
//
//	fixtures [-check] [-seat-scenarios dir]
//
// The directory defaults to the game client's seat scenarios, relative to backend/game_v2. It
// writes every transcript and removes the ones no scenario produces; with -check nothing is
// written, and it exits 1 naming each transcript that differs from what the server sends now, is
// missing, or has no scenario. It exits 2 on a usage error, and 1 when a scenario fails.
//
// Ported from ronin's Python seat scenario generator and its harness.
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

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("fixtures", flag.ContinueOnError)
	flags.SetOutput(stderr)
	check := flags.Bool("check", false, "fail on drift instead of writing the transcripts")
	seatDir := flags.String("seat-scenarios", "../../frontend/game_v2/src/fixtures/seat-scenarios",
		"directory of the seat transcripts")
	if flags.Parse(args) != nil || flags.NArg() > 0 {
		return exitUsage
	}

	logger := slog.New(slog.NewTextHandler(stderr, &slog.HandlerOptions{Level: slog.LevelWarn}))
	generated, err := generateSeatTranscripts(ctx, logger)
	if err != nil {
		return report(stderr, "seat scenario failed: "+err.Error()+"\n", exitFailed)
	}

	dir := fixtureDir{path: *seatDir, suffix: ".json"}
	if !*check {
		return writeTranscripts(dir, generated, stdout, stderr)
	}

	problems, err := dir.drift(generated)
	if err != nil {
		return report(stderr, "read the seat transcripts: "+err.Error()+"\n", exitFailed)
	}
	if len(problems) > 0 {
		var lines strings.Builder
		for _, problem := range problems {
			lines.WriteString(problem + "\n")
		}
		lines.WriteString("seat transcripts drifted from the server: regenerate them and update the client\n")
		return report(stdout, lines.String(), exitFailed)
	}
	return report(stdout, fmt.Sprintf("%d seat transcript(s) up to date\n", len(generated)), 0)
}

func writeTranscripts(dir fixtureDir, generated map[string][]byte, stdout, stderr io.Writer) int {
	removed, err := dir.write(generated)
	var lines strings.Builder
	for _, name := range removed {
		lines.WriteString("removed " + name + "\n")
	}
	if err != nil {
		return report(stderr, lines.String()+"write the seat transcripts: "+err.Error()+"\n", exitFailed)
	}
	fmt.Fprintf(&lines, "wrote %d seat transcript(s) to %s\n", len(generated), dir.path)
	return report(stdout, lines.String(), 0)
}

func report(w io.Writer, text string, code int) int {
	_, err := io.WriteString(w, text)
	if err != nil {
		return exitFailed
	}
	return code
}
