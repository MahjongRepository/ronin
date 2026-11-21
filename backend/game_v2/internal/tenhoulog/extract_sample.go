//go:build ignore

// The extract_sample command writes testdata/sample.jsonl.gz, the committed sample of real Tenhou
// wins the tenhoulog tests check, whole rounds only, so a double ron keeps both wins: the rounds of
// the first shard's first 2000 wins, then from every shard in order each round with a win holding
// a Tenhou yaku id, a yakuman id or a fu value taken fewer than 60 times so far or a pao seat, and
// the first 60 double rons.
//
// Run from this directory: go run extract_sample.go <agari dir>, the dir holding the
// agari-000NN.jsonl shards that ~/work/mahjong-rs/thoughts/_benchmark/unpack_agari.py writes from
// the 2025 phoenix-room logs into ~/work/mahjong-rs/thoughts/_benchmark/agari.
package main

import (
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhoulog"
)

const (
	leadingWins = 2000
	perFeature  = 60
	doubleRon   = "double ron"
	outputPath  = "testdata/sample.jsonl.gz"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: go run extract_sample.go <agari dir>")
		os.Exit(2)
	}
	err := extract(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func extract(dir string) error {
	shards, err := filepath.Glob(filepath.Join(dir, "agari-*.jsonl"))
	if err != nil {
		return err
	}
	slices.Sort(shards)
	if len(shards) == 0 {
		return fmt.Errorf("no agari shards in %s", dir)
	}

	var sample []tenhoulog.Win
	features := map[string]int{}
	for index, shard := range shards {
		rounds, readErr := readShard(shard)
		if readErr != nil {
			return readErr
		}
		for _, round := range rounds {
			isDoubleRon := len(round) > 1
			keep := (index == 0 && len(sample) < leadingWins) || (isDoubleRon && features[doubleRon] < perFeature)
			for _, win := range round {
				keep = keep || win.Pao != nil
				for _, feature := range featuresOf(win) {
					keep = keep || features[feature] < perFeature
				}
			}
			if !keep {
				continue
			}
			sample = append(sample, round...)
			if isDoubleRon {
				features[doubleRon]++
			}
			for _, win := range round {
				for _, feature := range featuresOf(win) {
					features[feature]++
				}
			}
		}
	}
	return write(sample)
}

func featuresOf(win tenhoulog.Win) []string {
	features := []string{fmt.Sprintf("fu %d", win.Fu)}
	for _, yaku := range win.Yaku {
		features = append(features, fmt.Sprintf("yaku %d", yaku[0]))
	}
	for _, yakuman := range win.Yakuman {
		features = append(features, fmt.Sprintf("yakuman %d", yakuman))
	}
	return features
}

func readShard(path string) ([][]tenhoulog.Win, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var rounds [][]tenhoulog.Win
	for round, readErr := range tenhoulog.Rounds(file) {
		if readErr != nil {
			return nil, fmt.Errorf("%s: %w", path, readErr)
		}
		rounds = append(rounds, round)
	}
	return rounds, nil
}

func write(sample []tenhoulog.Win) (err error) {
	file, err := os.Create(outputPath)
	if err != nil {
		return err
	}
	defer func() {
		err = errors.Join(err, file.Close())
	}()

	compressed := gzip.NewWriter(file)
	encoder := json.NewEncoder(compressed)
	for _, win := range sample {
		err = encoder.Encode(win)
		if err != nil {
			return err
		}
	}
	err = compressed.Close()
	if err != nil {
		return err
	}
	fmt.Printf("%d wins written to %s\n", len(sample), outputPath)
	return nil
}
