package session

import (
	"errors"
	"slices"
	"testing"
	"testing/synctest"
	"time"
)

func TestRetryStoreWrite_WhenTheFirstTwoAttemptsFail_ShouldSucceedOnTheThirdAfterOneAndTwoSeconds(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		start := time.Now()
		var attemptsAt []time.Duration
		write := func() error {
			attemptsAt = append(attemptsAt, time.Since(start))
			if len(attemptsAt) < 3 {
				return errors.New("database is locked")
			}

			return nil
		}

		err := retryStoreWrite(t.Context(), SystemClock(), write)
		if err != nil {
			t.Errorf("retryStoreWrite = %v, want nil", err)
		}
		if want := []time.Duration{0, time.Second, 3 * time.Second}; !slices.Equal(attemptsAt, want) {
			t.Errorf("attempts at %v, want %v", attemptsAt, want)
		}
	})
}
