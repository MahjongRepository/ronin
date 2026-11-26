package messaging

import (
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func with(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	return withAll(m, wire.Field{Key: k, Value: v})
}

func withAll(m wire.Map, stamps ...wire.Field) wire.Map {
	stamped := make(wire.Map, len(m), len(m)+len(stamps))
	copy(stamped, m)
	for _, stamp := range stamps {
		replaced := false
		for i := range stamped {
			if stamped[i].Key == stamp.Key {
				stamped[i].Value, replaced = stamp.Value, true
			}
		}
		if !replaced {
			stamped = append(stamped, stamp)
		}
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
