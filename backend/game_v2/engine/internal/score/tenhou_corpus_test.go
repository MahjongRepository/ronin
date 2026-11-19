//go:build tenhou

package score_test

import (
	"os"
	"path/filepath"
	"slices"
	"testing"
)

func TestEstimateHandValue_WhenTheWholeTenhouCorpusIsScored_ShouldMatchTenhouHanAndFuOnEveryWin(t *testing.T) {
	dir := os.Getenv("TENHOU_AGARI_DIR")
	if dir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			t.Fatalf("UserHomeDir error = %v", err)
		}
		dir = filepath.Join(home, "work", "mahjong-rs", "thoughts", "_benchmark", "agari")
	}
	shards, err := filepath.Glob(filepath.Join(dir, "agari-*.jsonl"))
	if err != nil || len(shards) == 0 {
		t.Fatalf("no agari shards in %s (set TENHOU_AGARI_DIR): %v", dir, err)
	}
	slices.Sort(shards)

	var wins, hanFuWins, mismatches int
	for _, shard := range shards {
		file, openErr := os.Open(shard)
		if openErr != nil {
			t.Fatalf("open %s: %v", shard, openErr)
		}
		check, checkErr := checkTenhouWins(file)
		closeErr := file.Close()
		if checkErr != nil || closeErr != nil {
			t.Fatalf("read %s: %v %v", shard, checkErr, closeErr)
		}

		wins += check.wins
		hanFuWins += check.hanFuWins
		mismatches += len(check.mismatches)
		for _, mismatch := range check.mismatches[:min(len(check.mismatches), 20)] {
			t.Error(mismatch)
		}
	}

	t.Logf("%d wins, %d checked on han and fu, %d mismatches", wins, hanFuWins, mismatches)
	if mismatches > 0 {
		t.Errorf("%d of %d wins disagree with Tenhou", mismatches, wins)
	}
}
