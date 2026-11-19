package messaging_test

import (
	"slices"
	"strconv"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	handSize       = 13
	dealBlocks     = 3
	dealBlockSize  = 4
	dealRoundSize  = tile.SeatCount * dealBlockSize
	finalDealStart = dealBlocks * dealRoundSize
	firstDrawSlot  = tile.SeatCount * handSize
)

func id(t *testing.T, n int) tile.TileID {
	t.Helper()
	got, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
	}
	return got
}

func ids(t *testing.T, ns ...int) []tile.TileID {
	t.Helper()
	got := make([]tile.TileID, 0, len(ns))
	for _, n := range ns {
		got = append(got, id(t, n))
	}
	return got
}

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}
	return got
}

func copies(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}
	var seen [tile.KindCount]int
	got := make([]tile.TileID, 0, len(parsed))
	for _, p := range parsed {
		kind := p.Kind()
		got = append(got, id(t, int(kind)*tile.CopiesPerKind+first+seen[kind]))
		seen[kind]++
	}
	return got
}

func with(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	replaced := slices.Clone(m)
	for i := range replaced {
		if replaced[i].Key == k {
			replaced[i].Value = v
		}
	}
	return replaced
}

func field(t *testing.T, m wire.Map, k wire.Key) wire.Value {
	t.Helper()
	v, ok := m.Get(k)
	if !ok {
		t.Fatalf("%v has no %v", m, k)
	}
	return v
}

func keys(m wire.Map) []wire.Key {
	got := make([]wire.Key, 0, len(m))
	for _, f := range m {
		got = append(got, f.Key)
	}
	return got
}

func assertMap(t *testing.T, what string, got, want wire.Map) {
	t.Helper()
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("%s differs (-want +got):\n%s", what, diff)
	}
}

func scores(points ...int) wire.StrMap {
	m := make(wire.StrMap, 0, len(points))
	for i, p := range points {
		m = append(m, wire.StrField{Key: strconv.Itoa(i), Value: wire.Int(p)})
	}
	return m
}

func intArray(ns ...int) wire.Array {
	a := make(wire.Array, 0, len(ns))
	for _, n := range ns {
		a = append(a, wire.Int(n))
	}
	return a
}

func junk(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "1357m2468p13579s")
}

func dealSlot(offset, i int) int {
	if block := i / dealBlockSize; block < dealBlocks {
		return block*dealRoundSize + offset*dealBlockSize + i%dealBlockSize
	}
	return finalDealStart + offset
}

func fixedWall(t *testing.T, hands [tile.SeatCount][]tile.TileID, draws []tile.TileID) [tile.TileIDCount]tile.TileID {
	t.Helper()
	var slots [tile.TileIDCount]tile.TileID
	var filled [tile.TileIDCount]bool
	var placed []tile.TileID
	place := func(slot int, at tile.TileID) {
		if slices.Contains(placed, at) {
			t.Fatalf("wall places tile %d twice", at.Index())
		}
		slots[slot], filled[slot] = at, true
		placed = append(placed, at)
	}
	for _, s := range tile.Seats() {
		for i, held := range hands[s.Index()] {
			place(dealSlot(s.Index(), i), held)
		}
	}
	for i, drawn := range draws {
		place(firstDrawSlot+i, drawn)
	}

	var free []tile.TileID
	for _, unplaced := range tile.AllTileIDs() {
		if !slices.Contains(placed, unplaced) {
			free = append(free, unplaced)
		}
	}
	for slot := range slots {
		if !filled[slot] {
			slots[slot], free = free[0], free[1:]
		}
	}
	return slots
}

func newFixedGame(t *testing.T, walls ...[tile.TileIDCount]tile.TileID) (engine.Game, []play.Emitted) {
	t.Helper()
	g, events, err := engine.NewGame(engine.Setup{Walls: play.Fixed{Walls: walls}})
	if err != nil {
		t.Fatalf("NewGame error = %v", err)
	}
	return g, events
}

func act(t *testing.T, g engine.Game, s tile.Seat, a play.Action) (engine.Game, []play.Emitted) {
	t.Helper()
	next, events, refusal := g.Act(s, a)
	if refusal.OK {
		t.Fatalf("seat %d %v refused: %+v", s.Index(), a, refusal.Value)
	}
	return next, events
}

func playDefaultsUntilRoundOver(t *testing.T, g engine.Game) engine.Game {
	t.Helper()
	for {
		switch awaiting := g.Awaiting().(type) {
		case play.AwaitingTurn:
			d, _ := g.Decision(awaiting.Seat)
			g, _ = act(t, g, awaiting.Seat, d.Default)
		case play.AwaitingCall:
			d, _ := g.Decision(awaiting.Seats[0])
			g, _ = act(t, g, awaiting.Seats[0], d.Default)
		case play.AwaitingRoundOver, play.AwaitingGameOver:
			return g
		}
	}
}

func testRoster() messaging.Roster {
	return messaging.Roster{GameID: "game1", Names: [tile.SeatCount]string{"Alice", "Bob", "Charlie", "Dave"}}
}
