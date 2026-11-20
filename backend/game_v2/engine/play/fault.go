package play

// EngineFaultError is an engine state its rules say cannot happen, such as the scorer rejecting a
// hand the round judged a win. The engine panics with it by value and never returns it; the
// session fails the game.
type EngineFaultError struct {
	Err error
}

// Error returns "engine fault: " followed by Err's text.
func (e EngineFaultError) Error() string {
	return "engine fault: " + e.Err.Error()
}

// Unwrap returns Err.
func (e EngineFaultError) Unwrap() error {
	return e.Err
}
