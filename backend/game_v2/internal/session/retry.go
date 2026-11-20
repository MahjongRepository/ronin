package session

import (
	"context"
	"errors"
	"time"
)

var storeRetryWaits = [...]time.Duration{time.Second, 2 * time.Second}

func retryStoreWrite(ctx context.Context, clock Clock, write func() error) error {
	err := protect(write)
	for _, wait := range storeRetryWaits {
		if err == nil {
			return nil
		}
		waited := make(chan struct{})
		stop := clock.AfterFunc(wait, func() { close(waited) })
		select {
		case <-waited:
		case <-ctx.Done():
			stop()
			return errors.Join(err, ctx.Err())
		}
		err = protect(write)
	}
	return err
}
