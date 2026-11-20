package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestWatchedFile_WhenTheLogIsRotatedAway_ShouldReopenItsPath(t *testing.T) {
	dir := t.TempDir()
	now := time.Unix(0, 0)
	w, err := openWatchedFile(dir, func() time.Time { return now })
	if err != nil {
		t.Fatalf("openWatchedFile error = %v", err)
	}
	t.Cleanup(func() { _ = w.Close() })
	path := filepath.Join(dir, "app.log")

	_, err = w.Write([]byte("before\n"))
	if err != nil {
		t.Fatalf("Write error = %v", err)
	}
	err = os.Rename(path, path+".1")
	if err != nil {
		t.Fatalf("rotate: %v", err)
	}
	_, err = w.Write([]byte("within\n"))
	if err != nil {
		t.Fatalf("Write error = %v", err)
	}
	now = now.Add(movedCheckInterval)
	_, err = w.Write([]byte("after\n"))
	if err != nil {
		t.Fatalf("Write error = %v", err)
	}

	rotated, _ := os.ReadFile(path + ".1")
	current, _ := os.ReadFile(path)
	if string(rotated) != "before\nwithin\n" || string(current) != "after\n" {
		t.Errorf("rotated %q and current %q, want writes within the check interval in the moved file "+
			"and the first write after it in a new app.log", rotated, current)
	}
}
