package tenhou

import (
	"fmt"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type reader struct {
	err error
}

type fieldError struct {
	key  wire.Key
	want string
}

func (e fieldError) Error() string {
	return "field " + e.key.String() + " is not " + e.want
}

func (r *reader) fail(err error) {
	if r.err == nil {
		r.err = err
	}
}

func field[T wire.Value](r *reader, m wire.Map, k wire.Key, want string) T {
	v, _ := m.Get(k)
	value, ok := v.(T)
	if !ok {
		r.fail(fieldError{key: k, want: want})
	}
	return value
}

func (r *reader) int(m wire.Map, k wire.Key) int {
	return int(field[wire.Int](r, m, k, "an integer"))
}

func (r *reader) str(m wire.Map, k wire.Key) string {
	return string(field[wire.Str](r, m, k, "a string"))
}

func (r *reader) boolean(m wire.Map, k wire.Key) bool {
	return bool(field[wire.Bool](r, m, k, "a boolean"))
}

func (r *reader) bin(m wire.Map, k wire.Key) []byte {
	return field[wire.Bin](r, m, k, "binary data")
}

func (r *reader) object(m wire.Map, k wire.Key) wire.Map {
	return field[wire.Map](r, m, k, "an object")
}

func (r *reader) seat(m wire.Map, k wire.Key) tile.Seat {
	s, ok := tile.NewSeat(r.int(m, k))
	if !ok {
		r.fail(fieldError{key: k, want: "a seat"})
	}
	return s
}

func (r *reader) tileID(m wire.Map, k wire.Key) int {
	id, ok := tile.NewTileID(r.int(m, k))
	if !ok {
		r.fail(fieldError{key: k, want: "a tile"})
	}
	return id.Index()
}

func (r *reader) ints(m wire.Map, k wire.Key) []int {
	items := field[wire.Array](r, m, k, "an array")
	values := make([]int, 0, len(items))
	for _, item := range items {
		n, ok := item.(wire.Int)
		if !ok {
			r.fail(fieldError{key: k, want: "an array of integers"})
		}
		values = append(values, int(n))
	}
	return values
}

func (r *reader) pair(m wire.Map, k wire.Key) [2]int {
	values := r.ints(m, k)
	if len(values) != len([2]int{}) {
		r.fail(fieldError{key: k, want: "a pair"})
		return [2]int{}
	}
	return [2]int(values)
}

func (r *reader) objects(m wire.Map, k wire.Key) []wire.Map {
	items := field[wire.Array](r, m, k, "an array")
	objects := make([]wire.Map, 0, len(items))
	for _, item := range items {
		object, ok := item.(wire.Map)
		if !ok {
			r.fail(fieldError{key: k, want: "an array of objects"})
		}
		objects = append(objects, object)
	}
	return objects
}

func (r *reader) scoreMap(m wire.Map, k wire.Key) [tile.SeatCount]int {
	scores := field[wire.StrMap](r, m, k, "a score map")
	var bySeat [tile.SeatCount]int
	for i := range bySeat {
		v, _ := scores.Get(strconv.Itoa(i))
		n, ok := v.(wire.Int)
		if !ok {
			r.fail(fmt.Errorf("score map %s has no score of seat %d", k, i))
		}
		bySeat[i] = int(n)
	}
	return bySeat
}
