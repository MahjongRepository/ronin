package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRunProfiled_WhenTheRunFails_ShouldStillWriteEveryProfileAndTheRuntimeStats(t *testing.T) {
	t.Setenv("GAME_REPLAY_DIR", "")
	dir := t.TempDir()

	err := runProfiled(t.Context(), "127.0.0.1:0", dir)

	if err == nil {
		t.Fatal("runProfiled error = nil, want the missing GAME_REPLAY_DIR")
	}
	for _, name := range []string{cpuProfileFile, allocsProfileFile, mutexProfileFile} {
		info, statErr := os.Stat(filepath.Join(dir, name))
		if statErr != nil || info.Size() == 0 {
			t.Errorf("profile %s: %v, size %v, want a written profile", name, statErr, info)
		}
	}
	data, readErr := os.ReadFile(filepath.Join(dir, runtimeStatsFile))
	var stats runtimeStats
	if readErr != nil || json.Unmarshal(data, &stats) != nil || stats.BusyCPUSeconds <= 0 || stats.AllocBytes == 0 {
		t.Errorf("runtime stats %q (read error %v), want some CPU and allocation", data, readErr)
	}
}
