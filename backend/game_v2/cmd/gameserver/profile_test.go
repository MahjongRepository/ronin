package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestRunProfiled_WhenTheRunFails_ShouldStillWriteEveryProfileAndTheRuntimeStats(t *testing.T) {
	dir := t.TempDir()
	unset := func(string) string { return "" }

	err := runProfiled(t.Context(), unset, "127.0.0.1:0", dir)
	if !errors.Is(err, errMissing) {
		t.Fatalf("runProfiled error = %v, want the missing GAME_REPLAY_DIR", err)
	}

	for _, name := range []string{cpuProfileFile, allocsProfileFile, mutexProfileFile} {
		info, statErr := os.Stat(filepath.Join(dir, name))
		if statErr != nil || info.Size() == 0 {
			t.Errorf("profile %s: %v, size %v, want a written profile", name, statErr, info)
		}
	}

	data, readErr := os.ReadFile(filepath.Join(dir, runtimeStatsFile))
	if readErr != nil {
		t.Fatalf("read runtime stats: %v", readErr)
	}

	var stats runtimeStats
	decodeErr := json.Unmarshal(data, &stats)
	if decodeErr != nil || stats.BusyCPUSeconds <= 0 || stats.AllocBytes == 0 {
		t.Errorf("runtime stats %q (decode error %v), want some CPU and allocation", data, decodeErr)
	}
}
