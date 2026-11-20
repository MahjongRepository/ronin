package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

const (
	logFileName = "app.log"
	logDirMode  = 0o755
	logFileMode = 0o644

	movedCheckInterval = time.Second
)

type watchedFile struct {
	mu        sync.Mutex
	path      string
	file      *os.File
	now       func() time.Time
	checkedAt time.Time
}

func openWatchedFile(dir string, now func() time.Time) (*watchedFile, error) {
	err := os.MkdirAll(dir, logDirMode)
	if err != nil {
		return nil, fmt.Errorf("create log dir %s: %w", dir, err)
	}
	w := &watchedFile{path: filepath.Join(dir, logFileName), now: now, checkedAt: now()}
	err = w.reopen()
	if err != nil {
		return nil, err
	}
	return w, nil
}

func (w *watchedFile) reopen() error {
	file, err := os.OpenFile(w.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, logFileMode)
	if err != nil {
		return fmt.Errorf("open log file %s: %w", w.path, err)
	}
	old := w.file
	w.file = file
	if old == nil {
		return nil
	}
	err = old.Close()
	if err != nil {
		return fmt.Errorf("close moved log file %s: %w", w.path, err)
	}
	return nil
}

func (w *watchedFile) reopenIfMoved() error {
	now := w.now()
	if now.Sub(w.checkedAt) < movedCheckInterval {
		return nil
	}
	w.checkedAt = now
	if !w.moved() {
		return nil
	}
	return w.reopen()
}

func (w *watchedFile) moved() bool {
	onDisk, err := os.Stat(w.path)
	if err != nil {
		return true
	}
	open, err := w.file.Stat()
	return err != nil || !os.SameFile(onDisk, open)
}

// Write appends p to the file, first reopening it when it was moved or removed, checked at most once per
// movedCheckInterval.
func (w *watchedFile) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	err := w.reopenIfMoved()
	if err != nil {
		return 0, err
	}
	return w.file.Write(p)
}

// Close closes the open file.
func (w *watchedFile) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	return w.file.Close()
}
