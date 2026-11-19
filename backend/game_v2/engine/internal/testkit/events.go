package testkit

import (
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// EventKinds returns a name for each event, in order: "started" for a game or round start, "drew"
// for a draw or its notice, else the event's own name.
func EventKinds(events []play.Emitted) []string {
	kinds := make([]string, 0, len(events))
	for _, emitted := range events {
		var kind string
		switch emitted.Event.(type) {
		case play.GameStarted, play.RoundStarted:
			kind = "started"
		case play.Drew, play.DrewNotice:
			kind = "drew"
		case play.Discarded:
			kind = "discarded"
		case play.RiichiDeposited:
			kind = "riichi_deposited"
		case play.FuritenChanged:
			kind = "furiten_changed"
		case play.Called:
			kind = "called"
		case play.PaoAssigned:
			kind = "pao_assigned"
		case play.DoraRevealed:
			kind = "dora_revealed"
		case play.RoundEnded:
			kind = "round_ended"
		case play.GameEnded:
			kind = "game_ended"
		}
		kinds = append(kinds, kind)
	}
	return kinds
}

// CalledMelds returns the Called events, in order.
func CalledMelds(events []play.Emitted) []play.Called {
	var called []play.Called
	for _, emitted := range events {
		if event, ok := emitted.Event.(play.Called); ok {
			called = append(called, event)
		}
	}
	return called
}

// FuritenChanges returns the FuritenChanged events, in order.
func FuritenChanges(events []play.Emitted) []play.FuritenChanged {
	var changes []play.FuritenChanged
	for _, emitted := range events {
		if event, ok := emitted.Event.(play.FuritenChanged); ok {
			changes = append(changes, event)
		}
	}
	return changes
}

// RoundResult returns the result of the first RoundEnded event; false without one.
func RoundResult(events []play.Emitted) (play.RoundResult, bool) {
	for _, emitted := range events {
		if event, ok := emitted.Event.(play.RoundEnded); ok {
			return event.Result, true
		}
	}
	return nil, false
}

// FirstWin returns the first win of the first RoundEnded event; false when the round did not end
// in a win.
func FirstWin(events []play.Emitted) (play.WinResult, bool) {
	result, _ := RoundResult(events)
	var wins []play.WinResult
	switch r := result.(type) {
	case play.Tsumo:
		wins = []play.WinResult{r.Win}
	case play.Ron:
		wins = r.Wins
	case play.ExhaustiveDraw, play.Abortive:
	}
	if len(wins) == 0 {
		return play.WinResult{}, false
	}
	return wins[0], true
}

// DoraReveals returns the indicators of the DoraRevealed events, in order.
func DoraReveals(events []play.Emitted) []tile.TileID {
	var indicators []tile.TileID
	for _, emitted := range events {
		if event, ok := emitted.Event.(play.DoraRevealed); ok {
			indicators = append(indicators, event.Indicator)
		}
	}
	return indicators
}

// DrawnRinshan returns the rinshan Drew events, in order.
func DrawnRinshan(events []play.Emitted) []play.Drew {
	var draws []play.Drew
	for _, emitted := range events {
		if event, ok := emitted.Event.(play.Drew); ok && event.Rinshan {
			draws = append(draws, event)
		}
	}
	return draws
}
