//go:build ignore

// The extract_tenhou_sample command writes testdata/tenhou_sample.jsonl.gz, the committed sample
// of real Tenhou wins the score tests check: the first 2000 wins of the first shard, then from
// every shard in order each win holding a Tenhou yaku id, a yakuman id or a fu value taken fewer
// than 60 times so far, each win once, with only the fields the tests read.
//
// Run from this directory: go run extract_tenhou_sample.go <agari dir>, the dir holding the
// agari-000NN.jsonl shards that ~/work/mahjong-rs/thoughts/_benchmark/unpack_agari.py writes from
// the 2025 phoenix-room logs into ~/work/mahjong-rs/thoughts/_benchmark/agari.
package main

import (
	"bufio"
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
)

const (
	leadingWins = 2000
	perFeature  = 60
	outputPath  = "testdata/tenhou_sample.jsonl.gz"
)

type sampleMeld struct {
	Kind  string `json:"kind"`
	Tiles []int  `json:"tiles"`
}

type sampleWin struct {
	ID             string       `json:"id"`
	Aka            bool         `json:"aka"`
	Kuitan         bool         `json:"kuitan"`
	RoundWind      int          `json:"round_wind"`
	SeatWind       int          `json:"seat_wind"`
	Honba          int          `json:"honba"`
	RiichiSticks   int          `json:"riichi_sticks"`
	Tsumo          bool         `json:"tsumo"`
	Closed         []int        `json:"closed"`
	Melds          []sampleMeld `json:"melds"`
	WinTile        int          `json:"win_tile"`
	DoraIndicators []int        `json:"dora_indicators"`
	UraIndicators  []int        `json:"ura_indicators"`
	Fu             int          `json:"fu"`
	Yaku           [][2]int     `json:"yaku"`
	Yakuman        []int        `json:"yakuman"`
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: go run extract_tenhou_sample.go <agari dir>")
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

	var sample []sampleWin
	taken := map[string]bool{}
	features := map[string]int{}
	for index, shard := range shards {
		wins, readErr := readShard(shard)
		if readErr != nil {
			return readErr
		}
		for position, win := range wins {
			if taken[win.ID] {
				continue
			}
			keep := index == 0 && position < leadingWins
			for _, feature := range featuresOf(win) {
				if features[feature] < perFeature {
					keep = true
				}
			}
			if !keep {
				continue
			}
			taken[win.ID] = true
			sample = append(sample, win)
			for _, feature := range featuresOf(win) {
				features[feature]++
			}
		}
	}
	return write(sample)
}

func featuresOf(win sampleWin) []string {
	features := []string{fmt.Sprintf("fu %d", win.Fu)}
	for _, yaku := range win.Yaku {
		features = append(features, fmt.Sprintf("yaku %d", yaku[0]))
	}
	for _, yakuman := range win.Yakuman {
		features = append(features, fmt.Sprintf("yakuman %d", yakuman))
	}
	return features
}

func readShard(path string) ([]sampleWin, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var wins []sampleWin
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1<<20), 1<<20)
	for scanner.Scan() {
		var win sampleWin
		err = json.Unmarshal(scanner.Bytes(), &win)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
		wins = append(wins, win)
	}
	return wins, scanner.Err()
}

func write(sample []sampleWin) (err error) {
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
