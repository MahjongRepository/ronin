package main

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

const (
	logFileName = "app.log"
	logDirMode  = 0o755
	logFileMode = 0o644
)

type watchedFile struct {
	mu   sync.Mutex
	path string
	file *os.File
}

func openWatchedFile(dir string) (*watchedFile, error) {
	err := os.MkdirAll(dir, logDirMode)
	if err != nil {
		return nil, fmt.Errorf("create log dir %s: %w", dir, err)
	}
	w := &watchedFile{path: filepath.Join(dir, logFileName)}
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
	if w.file != nil {
		_ = w.file.Close()
	}
	w.file = file
	return nil
}

func (w *watchedFile) moved() bool {
	onDisk, err := os.Stat(w.path)
	if err != nil {
		return true
	}
	open, err := w.file.Stat()
	return err != nil || !os.SameFile(onDisk, open)
}

// Write appends p to the file, reopening it first when it was moved or removed.
func (w *watchedFile) Write(p []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.moved() {
		err := w.reopen()
		if err != nil {
			return 0, err
		}
	}
	return w.file.Write(p)
}

// Close closes the open file.
func (w *watchedFile) Close() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	return w.file.Close()
}
