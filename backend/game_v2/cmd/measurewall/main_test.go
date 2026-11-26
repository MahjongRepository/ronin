package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func runMeasurement(t *testing.T, args ...string) string {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := run(args, &stdout, &stderr)
	if code != 0 {
		t.Fatalf("run(%v) = %d, stderr %q", args, code, stderr.String())
	}

	return stdout.String()
}

func withoutElapsedLine(report string) string {
	lines := strings.Split(report, "\n")
	kept := lines[:0]
	for _, line := range lines {
		if !strings.HasPrefix(line, "  elapsed ") {
			kept = append(kept, line)
		}
	}

	return strings.Join(kept, "\n")
}

func TestRun_WhenGivenThePythonMeasurementsArguments_ShouldPrintItsReport(t *testing.T) {
	want, err := os.ReadFile(filepath.Join("testdata", "python_report.txt"))
	if err != nil {
		t.Fatalf("read the Python report: %v", err)
	}

	got := runMeasurement(t, "-games", "200", "-rounds", "3", "-experiment-seed", "5")
	if diff := cmp.Diff(string(want), withoutElapsedLine(got)); diff != "" {
		t.Errorf("report differs from the Python measurement's (-python +go):\n%s", diff)
	}
}

func TestRun_WhenTheBaselineIsARunOfTheSameSeed_ShouldShowNoDifference(t *testing.T) {
	baseline := filepath.Join(t.TempDir(), "baseline.json")
	runMeasurement(t, "-games", "40", "-rounds", "2", "-json", baseline)

	got := runMeasurement(t, "-games", "40", "-rounds", "2", "-baseline", baseline)

	_, comparison, found := strings.Cut(got, "\nBASELINE ")
	if !found {
		t.Fatalf("report has no baseline comparison:\n%s", got)
	}

	rows := strings.Split(strings.TrimSpace(comparison), "\n")[3:]
	if len(rows) == 0 {
		t.Fatalf("baseline comparison has no rows:\n%s", comparison)
	}

	for _, row := range rows {
		if !strings.HasSuffix(row, " 0.0000") {
			t.Errorf("baseline row %q, want a difference of 0.0000", row)
		}
	}
}

func TestObserveEngine_WhenTheDealerDrawIsNotTheLiveWallsNextTile_ShouldRecordAStructuralErrorAndSkipTheWall(t *testing.T) {
	game, err := sampleEngineGame(strings.Repeat("ab", 96), 2)
	if err != nil {
		t.Fatalf("sampleEngineGame error = %v", err)
	}

	game.rounds[1].deal.DealerDraw = game.rounds[1].deal.Live[dealtTiles+1]
	m := newMeasurement()

	err = m.observeEngine(game)
	if err != nil {
		t.Fatalf("observeEngine error = %v", err)
	}

	if m.walls != 1 || len(m.errors) != 1 {
		t.Errorf("observeEngine counted %d walls and errors %q, want 1 wall and one error", m.walls, m.errors)
	}
}
