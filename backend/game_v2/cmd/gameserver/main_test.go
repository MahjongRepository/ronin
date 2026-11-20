package main

import (
	"errors"
	"slices"
	"testing"
)

func leaves(err error) []error {
	if err == nil {
		return nil
	}
	joined, ok := err.(interface{ Unwrap() []error })
	if !ok {
		return []error{err}
	}
	var all []error
	for _, part := range joined.Unwrap() {
		all = append(all, leaves(part)...)
	}
	return all
}

func TestUnlogged_WhenPartsOfTheErrorWereLogged_ShouldKeepOnlyTheOthers(t *testing.T) {
	failure := errors.New("open database")
	logClose := errors.New("close the log file")
	profileClose := errors.New("close the CPU profile")
	tests := []struct {
		name string
		err  error
		want []error
	}{
		{
			"close errors joined to a logged run",
			errors.Join(errors.Join(loggedError{failure}, logClose), profileClose),
			[]error{logClose, profileClose},
		},
		{"a bare logged run", loggedError{failure}, nil},
		{"a plain failure", failure, []error{failure}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := unlogged(tc.err)

			if !slices.Equal(leaves(got), tc.want) {
				t.Errorf("unlogged(%q) = %q, want the parts %q", tc.err, got, tc.want)
			}
		})
	}
}
