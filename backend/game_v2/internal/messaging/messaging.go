// Package messaging shapes the game for the wire and reads what clients send: a client message
// parsed into the engine's action, every engine event shaped into its message, the opening that
// starts a seat's decision built from the decision alone, the reconnect snapshot built from a
// seat's view alone, and the session's and the game's error messages.
//
// The engine emits facts only, so every field a message names beyond them comes from the session
// (the roster, the wait ids, the timers) or is derived here from the engine's output, never from
// its state. Scores, payments and stick values go out in wire score units.
//
// Ported from ronin's Python game server: its messaging package (client message models, event
// payloads, serialization, openings, the reconnect snapshot and the game errors).
package messaging

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	riichiStickValue = 1000
	honbaPerWin      = 300
)

func with(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	stamped := make(wire.Map, 0, len(m)+1)
	replaced := false
	for _, f := range m {
		if f.Key == k {
			f.Value, replaced = v, true
		}
		stamped = append(stamped, f)
	}
	if !replaced {
		stamped = append(stamped, wire.Field{Key: k, Value: v})
	}
	return stamped
}

func seatValue(s tile.Seat) wire.Int {
	return wire.Int(s.Index())
}

func seatsValue(seats []tile.Seat) wire.Array {
	values := make(wire.Array, 0, len(seats))
	for _, s := range seats {
		values = append(values, seatValue(s))
	}
	return values
}

func tileValue(id tile.TileID) wire.Int {
	return wire.Int(id.Index())
}

func tilesValue(ids []tile.TileID) wire.Array {
	values := make(wire.Array, 0, len(ids))
	for _, id := range ids {
		values = append(values, tileValue(id))
	}
	return values
}

func kindsValue(kinds []tile.Kind) wire.Array {
	values := make(wire.Array, 0, len(kinds))
	for _, k := range kinds {
		values = append(values, wire.Int(k))
	}
	return values
}

func scoreValue(points int) wire.Int {
	return wire.Int(points / wire.ScoreDivisor)
}

func scoreMap(points [tile.SeatCount]int) wire.StrMap {
	scores := make(wire.StrMap, 0, tile.SeatCount)
	for _, s := range tile.Seats() {
		scores = append(scores, wire.StrField{Key: strconv.Itoa(s.Index()), Value: scoreValue(points[s.Index()])})
	}
	return scores
}

func diceValue(d tile.Dice) wire.Array {
	return wire.Array{wire.Int(d.First), wire.Int(d.Second)}
}

func optionField[T any](m wire.Map, k wire.Key, o play.Option[T], value func(T) wire.Value) wire.Map {
	if !o.OK {
		return m
	}
	return append(m, wire.Field{Key: k, Value: value(o.Value)})
}
