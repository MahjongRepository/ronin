package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRunProfiled_WhenTheRunFails_ShouldStillWriteTheProfile(t *testing.T) {
	t.Setenv("GAME_REPLAY_DIR", "")
	profile := filepath.Join(t.TempDir(), "cpu.prof")

	err := runProfiled(t.Context(), "127.0.0.1:0", profile)

	if err == nil {
		t.Fatal("runProfiled error = nil, want the missing GAME_REPLAY_DIR")
	}
	info, statErr := os.Stat(profile)
	if statErr != nil || info.Size() == 0 {
		t.Errorf("profile %s: %v, size %v, want a written profile", profile, statErr, info)
	}
}
