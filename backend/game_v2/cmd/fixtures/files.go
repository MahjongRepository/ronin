package main

import (
	"bytes"
	"errors"
	"io/fs"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"strings"
)

const fixtureFileMode = 0o644

type fixtureDir struct {
	path   string
	suffix string
}

func (d fixtureDir) committed() ([]string, error) {
	entries, err := os.ReadDir(d.path)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), d.suffix) {
			names = append(names, e.Name())
		}
	}
	return names, nil
}

func (d fixtureDir) drift(generated map[string][]byte) ([]string, error) {
	committed, err := d.committed()
	if err != nil {
		return nil, err
	}

	var problems []string
	for _, name := range committed {
		if _, produced := generated[name]; !produced {
			problems = append(problems, "orphaned: "+name+" (no scenario produces it)")
		}
	}
	for _, name := range slices.Sorted(maps.Keys(generated)) {
		if !slices.Contains(committed, name) {
			problems = append(problems, "missing: "+name)
			continue
		}

		content, readErr := os.ReadFile(filepath.Join(d.path, name))
		if readErr != nil {
			return nil, readErr
		}
		if !bytes.Equal(content, generated[name]) {
			problems = append(problems, "stale: "+name)
		}
	}
	return problems, nil
}

func (d fixtureDir) write(generated map[string][]byte) (removed []string, err error) {
	err = os.MkdirAll(d.path, 0o755)
	if err != nil {
		return nil, err
	}
	committed, err := d.committed()
	if err != nil {
		return nil, err
	}

	for _, name := range committed {
		if _, produced := generated[name]; produced {
			continue
		}
		err = os.Remove(filepath.Join(d.path, name))
		if err != nil {
			return removed, err
		}
		removed = append(removed, name)
	}
	for _, name := range slices.Sorted(maps.Keys(generated)) {
		err = os.WriteFile(filepath.Join(d.path, name), generated[name], fixtureFileMode)
		if err != nil {
			return removed, err
		}
	}
	return removed, nil
}
