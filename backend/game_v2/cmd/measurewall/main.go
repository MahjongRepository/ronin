package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"runtime"
	"time"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
)

const (
	exitFailed    = 1
	exitUsage     = 2
	defaultGames  = 5000
	defaultRounds = 4
)

type options struct {
	games          int
	rounds         int
	experimentSeed int
	jsonPath       string
	baselinePath   string
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	opts, err := parseOptions(args, stderr)
	if err != nil {
		return exitUsage
	}

	m, meta, err := measure(opts)
	if err != nil {
		return fail(stderr, err)
	}

	r := m.report(meta)
	text := renderText(r) + "\n"
	if opts.baselinePath != "" {
		comparison, baselineErr := renderBaseline(r, opts.baselinePath)
		if baselineErr != nil {
			return fail(stderr, baselineErr)
		}

		text += "\n" + comparison + "\n"
	}

	if opts.jsonPath != "" {
		writeErr := writeJSON(opts.jsonPath, toJSON(r, m.familyJSON()))
		if writeErr != nil {
			return fail(stderr, writeErr)
		}

		text += "\nJSON written to " + opts.jsonPath + "\n"
	}

	_, err = io.WriteString(stdout, text)
	if err != nil {
		return fail(stderr, err)
	}

	if len(r.errors) > 0 {
		return exitFailed
	}

	return 0
}

func parseOptions(args []string, stderr io.Writer) (options, error) {
	flags := flag.NewFlagSet("measurewall", flag.ContinueOnError)
	flags.SetOutput(stderr)

	var opts options
	flags.IntVar(&opts.games, "games", defaultGames, "games to sample")
	flags.IntVar(&opts.rounds, "rounds", defaultRounds, "rounds (walls) per game")
	flags.IntVar(&opts.experimentSeed, "experiment-seed", 0, "fixes the engine seeds and the control shuffle")
	flags.StringVar(&opts.jsonPath, "json", "", "write the report with raw counts here")
	flags.StringVar(&opts.baselinePath, "baseline", "", "a JSON report of an earlier run to compare with")
	err := flags.Parse(args)
	if err != nil {
		return options{}, err
	}

	if flags.NArg() > 0 {
		err = fmt.Errorf("unexpected arguments: %v", flags.Args())
	}

	if opts.games < 1 || opts.rounds < 1 {
		err = errors.New("-games and -rounds must be at least 1")
	}

	if err != nil {
		_, _ = fmt.Fprintln(stderr, err)
	}

	return opts, err
}

func measure(opts options) (*measurement, metadata, error) {
	started := time.Now()
	m := newMeasurement()
	var first *gameSample
	for _, seed := range engineSeeds(opts.experimentSeed, opts.games) {
		game, err := sampleEngineGame(seed, opts.rounds)
		if err != nil {
			return nil, metadata{}, err
		}

		if first == nil {
			first = &game
		}

		err = m.observeEngine(game)
		if err != nil {
			return nil, metadata{}, err
		}
	}

	err := m.verifyRegeneration(*first)
	if err != nil {
		return nil, metadata{}, err
	}

	control := controlRounds(opts.experimentSeed, opts.games*opts.rounds)
	for start := 0; start < len(control); start += opts.rounds {
		err = m.observeControl(control[start : start+opts.rounds])
		if err != nil {
			return nil, metadata{}, err
		}
	}

	elapsed := time.Since(started).Seconds()
	wallsPerSecond := 0.0
	if elapsed > 0 {
		wallsPerSecond = float64(m.walls) / elapsed
	}

	meta := metadata{
		RNGVersion:     engine.RNGVersion,
		SeedBytes:      engine.SeedBytes,
		Games:          opts.games,
		Rounds:         opts.rounds,
		ExperimentSeed: opts.experimentSeed,
		ControlMethod:  controlName,
		Go:             runtime.Version(),
		StartedAt:      started.UTC().Format("2006-01-02T15:04:05-07:00"),
		ElapsedSeconds: elapsed,
		WallsPerSecond: wallsPerSecond,
	}
	return m, meta, nil
}

func writeJSON(path string, report reportJSON) error {
	data, err := json.Marshal(report)
	if err != nil {
		return fmt.Errorf("encode the report: %w", err)
	}

	err = os.WriteFile(path, data, 0o600)
	if err != nil {
		return fmt.Errorf("write %s: %w", path, err)
	}

	return nil
}

func fail(stderr io.Writer, err error) int {
	_, _ = fmt.Fprintln(stderr, err)
	return exitFailed
}
