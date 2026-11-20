package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"runtime/pprof"
)

func runProfiled(ctx context.Context, addr, cpuProfile string) (err error) {
	if cpuProfile == "" {
		return run(ctx, addr)
	}

	file, err := os.Create(cpuProfile)
	if err != nil {
		return fmt.Errorf("create the CPU profile: %w", err)
	}
	err = pprof.StartCPUProfile(file)
	if err != nil {
		return errors.Join(fmt.Errorf("start the CPU profile: %w", err), file.Close())
	}
	defer func() {
		pprof.StopCPUProfile()
		err = errors.Join(err, file.Close())
	}()
	return run(ctx, addr)
}
