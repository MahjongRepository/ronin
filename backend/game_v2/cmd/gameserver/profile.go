package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"runtime/metrics"
	"runtime/pprof"
)

const (
	cpuProfileFile       = "cpu.prof"
	allocsProfileFile    = "allocs.prof"
	mutexProfileFile     = "mutex.prof"
	runtimeStatsFile     = "runtime.json"
	mutexProfileFraction = 5
)

type runtimeStats struct {
	BusyCPUSeconds   float64 `json:"busy_cpu_seconds"`
	GCCPUSeconds     float64 `json:"gc_cpu_seconds"`
	GCCycles         uint64  `json:"gc_cycles"`
	AllocBytes       uint64  `json:"alloc_bytes"`
	AllocObjects     uint64  `json:"alloc_objects"`
	MutexWaitSeconds float64 `json:"mutex_wait_seconds"`
}

func runProfiled(ctx context.Context, addr, profileDir string) (err error) {
	if profileDir == "" {
		return run(ctx, addr)
	}

	file, err := os.Create(filepath.Join(profileDir, cpuProfileFile))
	if err != nil {
		return fmt.Errorf("create the CPU profile: %w", err)
	}
	err = pprof.StartCPUProfile(file)
	if err != nil {
		return errors.Join(fmt.Errorf("start the CPU profile: %w", err), file.Close())
	}
	runtime.SetMutexProfileFraction(mutexProfileFraction)
	defer func() {
		pprof.StopCPUProfile()
		err = errors.Join(err, file.Close(), writeRunProfiles(profileDir))
	}()
	return run(ctx, addr)
}

func writeRunProfiles(dir string) error {
	runtime.GC()
	return errors.Join(
		writeRuntimeStats(filepath.Join(dir, runtimeStatsFile)),
		writeProfile(filepath.Join(dir, allocsProfileFile), "allocs"),
		writeProfile(filepath.Join(dir, mutexProfileFile), "mutex"),
	)
}

func writeProfile(path, name string) (err error) {
	file, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create the %s profile: %w", name, err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()

	err = pprof.Lookup(name).WriteTo(file, 0)
	if err != nil {
		return fmt.Errorf("write the %s profile: %w", name, err)
	}
	return nil
}

func writeRuntimeStats(path string) error {
	stats, err := readRuntimeStats()
	if err != nil {
		return err
	}
	data, err := json.MarshalIndent(stats, "", "  ")
	if err != nil {
		return fmt.Errorf("encode the runtime stats: %w", err)
	}
	err = os.WriteFile(path, append(data, '\n'), 0o600)
	if err != nil {
		return fmt.Errorf("write the runtime stats: %w", err)
	}
	return nil
}

func readRuntimeStats() (runtimeStats, error) {
	samples := []metrics.Sample{
		{Name: "/cpu/classes/total:cpu-seconds"},
		{Name: "/cpu/classes/idle:cpu-seconds"},
		{Name: "/cpu/classes/gc/total:cpu-seconds"},
		{Name: "/gc/cycles/total:gc-cycles"},
		{Name: "/gc/heap/allocs:bytes"},
		{Name: "/gc/heap/allocs:objects"},
		{Name: "/sync/mutex/wait/total:seconds"},
	}
	metrics.Read(samples)
	for _, s := range samples {
		if s.Value.Kind() == metrics.KindBad {
			return runtimeStats{}, fmt.Errorf("read the runtime metric %s: not supported", s.Name)
		}
	}

	return runtimeStats{
		BusyCPUSeconds:   samples[0].Value.Float64() - samples[1].Value.Float64(),
		GCCPUSeconds:     samples[2].Value.Float64(),
		GCCycles:         samples[3].Value.Uint64(),
		AllocBytes:       samples[4].Value.Uint64(),
		AllocObjects:     samples[5].Value.Uint64(),
		MutexWaitSeconds: samples[6].Value.Float64(),
	}, nil
}
