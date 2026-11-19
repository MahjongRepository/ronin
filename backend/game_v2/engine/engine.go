// Package engine is the only public API of the game engine.
package engine

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"

// EventKind names what an Event reports.
type EventKind string

// EventGameStarted reports that a game began.
const EventGameStarted EventKind = "game_started"

// Event is one thing that happened in a game.
type Event struct {
	Kind          EventKind
	WallTileCount int
}

// ActionKind names what a seat asks to do.
type ActionKind string

// ActionDiscard asks to discard a tile.
const ActionDiscard ActionKind = "discard"

// Action is a seat's request to the game.
type Action struct {
	Kind ActionKind
}

// RefusalReason names why an Action was refused.
type RefusalReason string

// RefusalNotAwaited refuses an action from a seat the game is not waiting for.
const RefusalNotAwaited RefusalReason = "not_awaited"

// Refusal is the outcome of an Action the game did not accept.
type Refusal struct {
	Reason RefusalReason
}

// Game is one game, held by its caller.
type Game struct{}

// NewGame starts a game from seed and returns it with the events of its start.
func NewGame(_ string) (*Game, []Event) {
	started := Event{Kind: EventGameStarted, WallTileCount: rules.WallTileCount()}
	return &Game{}, []Event{started}
}

// Act applies a seat's action and returns its events, or the Refusal when the game does not accept it.
func (g *Game) Act(_ int, _ Action) ([]Event, *Refusal) {
	return nil, &Refusal{Reason: RefusalNotAwaited}
}
