// Package play is the vocabulary that crosses the engine's facade: the actions a seat answers
// with, the decision it answers, what the game awaits, the events it emits and to whom, the
// refusals, the round results and standings, the values and yaku of a win, and what one seat may
// see of the game. It imports only engine/tile, so the server side and every engine package can
// build on it.
//
// The sum types are sealed interfaces: an unexported marker method and one struct per variant, so
// a type switch over one lists every variant. An absent value is an Option, or nil for a sum type.
package play

// Option is a value that may be absent: Value holds it when OK is true. Its zero value is absent.
type Option[T any] struct {
	Value T
	OK    bool
}

// Some returns the present Option of v.
func Some[T any](v T) Option[T] {
	return Option[T]{Value: v, OK: true}
}
