//go:build tenhou

package tenhoulog_test

import (
	"maps"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou/tenhoulog"
)

func TestCompare_WhenTheWholeTenhouCorpusIsScored_ShouldAgreeWithTenhouOnEveryWin(t *testing.T) {
	dir := os.Getenv("TENHOU_AGARI_DIR")
	if dir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			t.Fatalf("UserHomeDir error = %v", err)
		}
		dir = filepath.Join(home, "work", "mahjong-rs", "thoughts", "_benchmark", "agari")
	}
	maxLogs := 0
	if limit := os.Getenv("TENHOU_MAX_LOGS"); limit != "" {
		parsed, err := strconv.Atoi(limit)
		if err != nil || parsed < 0 {
			t.Fatalf("TENHOU_MAX_LOGS = %q, want a count of logs, 0 for all", limit)
		}
		maxLogs = parsed
	}
	shards, err := filepath.Glob(filepath.Join(dir, "agari-*.jsonl"))
	if err != nil || len(shards) == 0 {
		t.Fatalf("no agari shards in %s (set TENHOU_AGARI_DIR): %v", dir, err)
	}
	slices.Sort(shards)

	corpus := corpusCheck{maxLogs: maxLogs, logs: map[string]bool{}, mismatches: map[tenhoulog.Check][]string{}}
	for _, shard := range shards {
		if corpus.full() {
			break
		}
		corpus.readShard(t, shard)
	}

	total := 0
	for _, check := range slices.Sorted(maps.Keys(corpus.mismatches)) {
		found := corpus.mismatches[check]
		total += len(found)
		t.Logf("%s: %d mismatches", check, len(found))
		for _, mismatch := range found[:min(len(found), 20)] {
			t.Error(mismatch)
		}
	}
	t.Logf("%d logs, %d wins, %d mismatches", len(corpus.logs), corpus.wins, total)
}

type corpusCheck struct {
	maxLogs    int
	logs       map[string]bool
	wins       int
	mismatches map[tenhoulog.Check][]string
}

func (c *corpusCheck) full() bool {
	return c.maxLogs > 0 && len(c.logs) >= c.maxLogs
}

func (c *corpusCheck) readShard(t *testing.T, shard string) {
	t.Helper()
	file, err := os.Open(shard)
	if err != nil {
		t.Fatalf("open %s: %v", shard, err)
	}
	defer func() {
		closeErr := file.Close()
		if closeErr != nil {
			t.Errorf("close %s: %v", shard, closeErr)
		}
	}()

	for round, readErr := range tenhoulog.Rounds(file) {
		if readErr != nil {
			t.Fatalf("read %s: %v", shard, readErr)
		}
		if !c.logs[round[0].LogID] {
			if c.full() {
				return
			}
			c.logs[round[0].LogID] = true
		}

		c.wins += len(round)
		for _, mismatch := range tenhoulog.Compare(round) {
			c.mismatches[mismatch.Check] = append(c.mismatches[mismatch.Check],
				string(mismatch.Check)+" "+mismatch.WinID+": "+mismatch.Detail)
		}
	}
}
