package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestWatchedFile_WhenTheLogIsRotatedAway_ShouldReopenItsPath(t *testing.T) {
	dir := t.TempDir()
	w, err := openWatchedFile(dir)
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
	_, err = w.Write([]byte("after\n"))
	if err != nil {
		t.Fatalf("Write error = %v", err)
	}

	rotated, _ := os.ReadFile(path + ".1")
	current, _ := os.ReadFile(path)
	if string(rotated) != "before\n" || string(current) != "after\n" {
		t.Errorf("rotated %q and current %q, want the write after the rotation in a new app.log", rotated, current)
	}
}
