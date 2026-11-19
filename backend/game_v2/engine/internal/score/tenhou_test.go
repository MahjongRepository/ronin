package score_test

import (
	"compress/gzip"
	"os"
	"testing"
)

func TestEstimateHandValue_WhenTheTenhouSampleIsScored_ShouldMatchTenhouHanAndFuOnEveryWin(t *testing.T) {
	file, err := os.Open("testdata/tenhou_sample.jsonl.gz")
	if err != nil {
		t.Fatalf("open the sample: %v", err)
	}
	defer func() {
		closeErr := file.Close()
		if closeErr != nil {
			t.Errorf("close the sample: %v", closeErr)
		}
	}()
	compressed, err := gzip.NewReader(file)
	if err != nil {
		t.Fatalf("read the sample: %v", err)
	}

	check, err := checkTenhouWins(compressed)
	if err != nil {
		t.Fatalf("checkTenhouWins error = %v", err)
	}

	if check.wins != 3464 || check.hanFuWins < 3000 {
		t.Errorf("the sample holds %d wins, %d without yakuman; want 3464, at least 3000", check.wins, check.hanFuWins)
	}
	for _, mismatch := range check.mismatches {
		t.Error(mismatch)
	}
}
