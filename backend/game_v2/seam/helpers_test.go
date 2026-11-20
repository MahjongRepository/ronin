package seam_test

import (
	"reflect"
	"slices"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	liveWallSize   = 122
	handSize       = 13
	dealBlocks     = 3
	dealBlockSize  = 4
	dealRoundSize  = tile.SeatCount * dealBlockSize
	finalDealStart = dealBlocks * dealRoundSize
	firstDrawSlot  = tile.SeatCount * handSize
	startingScore  = 25000
	tablePoints    = startingScore * tile.SeatCount
)

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}
	return got
}

func id(t *testing.T, n int) tile.TileID {
	t.Helper()
	got, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
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
	ids := make([]tile.TileID, 0, len(parsed))
	for _, parsedTile := range parsed {
		kind := parsedTile.Kind()
		ids = append(ids, id(t, int(kind)*tile.CopiesPerKind+first+seen[kind]))
		seen[kind]++
	}
	return ids
}

func copyOf(t *testing.T, first int, mpsz string) tile.TileID {
	t.Helper()
	ids := copies(t, first, mpsz)
	if len(ids) != 1 {
		t.Fatalf("%q holds %d tiles, want 1", mpsz, len(ids))
	}
	return ids[0]
}

func junk(t *testing.T, first int) []tile.TileID {
	t.Helper()
	return copies(t, first, "1357m2468p13579s")
}

type startWall struct {
	hands [tile.SeatCount][]tile.TileID
	draws []tile.TileID
}

func notenWall(t *testing.T) startWall {
	t.Helper()
	return startWall{hands: [tile.SeatCount][]tile.TileID{junk(t, 0), junk(t, 1), junk(t, 2), junk(t, 3)}}
}

func dealSlot(offset, i int) int {
	if block := i / dealBlockSize; block < dealBlocks {
		return block*dealRoundSize + offset*dealBlockSize + i%dealBlockSize
	}
	return finalDealStart + offset
}

func (w startWall) tiles(t *testing.T, dealer tile.Seat) [tile.TileIDCount]tile.TileID {
	t.Helper()
	if len(w.draws) > liveWallSize-firstDrawSlot {
		t.Fatalf("start wall holds %d draws", len(w.draws))
	}

	var slots [tile.TileIDCount]tile.TileID
	var filled [tile.TileIDCount]bool
	var placed []tile.TileID
	place := func(slot int, at tile.TileID) {
		if slices.Contains(placed, at) {
			t.Fatalf("start wall places tile %d twice", at.Index())
		}
		slots[slot], filled[slot] = at, true
		placed = append(placed, at)
	}
	for _, s := range tile.Seats() {
		if len(w.hands[s.Index()]) > handSize {
			t.Fatalf("start wall deals seat %d %d tiles", s.Index(), len(w.hands[s.Index()]))
		}
		for i, held := range w.hands[s.Index()] {
			place(dealSlot(s.DistanceFrom(dealer), i), held)
		}
	}
	for i, drawn := range w.draws {
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

func fixedSetup(t *testing.T, w startWall) engine.Setup {
	t.Helper()
	return engine.Setup{Walls: play.Fixed{Walls: [][tile.TileIDCount]tile.TileID{w.tiles(t, seat(t, 0))}}}
}

func seedOf(t *testing.T, pair string) engine.Seed {
	t.Helper()
	seed, err := engine.ParseSeed(strings.Repeat(pair, engine.SeedBytes))
	if err != nil {
		t.Fatalf("ParseSeed error = %v", err)
	}
	return seed
}

func seededSetup(t *testing.T, pair string) engine.Setup {
	t.Helper()
	return engine.Setup{Walls: play.Seeded{Seed: seedOf(t, pair)}}
}

func newGame(t *testing.T, setup engine.Setup) (engine.Game, []play.Emitted) {
	t.Helper()
	g, events, err := engine.NewGame(setup)
	if err != nil {
		t.Fatalf("NewGame error = %v", err)
	}
	return g, events
}

func act(t *testing.T, g engine.Game, s tile.Seat, action play.Action) (engine.Game, []play.Emitted) {
	t.Helper()
	next, events, refusal := g.Act(s, action)
	if refusal.OK {
		t.Fatalf("Act(seat %d, %v) refused: %v", s.Index(), action, refusal.Value)
	}
	return next, events
}

func dealNextRound(t *testing.T, g engine.Game) (engine.Game, []play.Emitted) {
	t.Helper()
	next, events, refusal := g.DealNextRound()
	if refusal.OK {
		t.Fatalf("DealNextRound refused: %v", refusal.Value)
	}
	return next, events
}

func begun(t *testing.T, g engine.Game) (engine.Game, []play.Emitted) {
	t.Helper()
	next, events, refusal := g.Begin()
	if refusal.OK {
		t.Fatalf("Begin refused: %v", refusal.Value)
	}
	return next, events
}

func dealOrBegin(t *testing.T, g engine.Game) (engine.Game, []play.Emitted) {
	t.Helper()
	if _, dealt := g.Awaiting().(play.AwaitingDealt); dealt {
		return begun(t, g)
	}
	return dealNextRound(t, g)
}

func turnSeat(t *testing.T, g engine.Game) tile.Seat {
	t.Helper()
	turn, ok := g.Awaiting().(play.AwaitingTurn)
	if !ok {
		t.Fatalf("Awaiting = %#v, want a turn", g.Awaiting())
	}
	return turn.Seat
}

func discardDrawn(t *testing.T, g engine.Game, turns int) engine.Game {
	t.Helper()
	for range turns {
		s := turnSeat(t, g)
		drawn := g.View(s).Record.Drawn
		if !drawn.OK {
			t.Fatalf("seat %d has drawn no tile", s.Index())
		}
		g, _ = act(t, g, s, play.DiscardAction(drawn.Value))
	}
	return g
}

func threePinWithTwoRonCallers(t *testing.T) engine.Game {
	t.Helper()
	g, _ := newGame(t, fixedSetup(t, threePinWall(t)))
	g, _ = begun(t, g)
	return discardDrawn(t, g, 3)
}

func threePinWall(t *testing.T) startWall {
	t.Helper()
	return startWall{
		hands: [tile.SeatCount][]tile.TileID{
			copies(t, 0, "123456789m1255p"),
			copies(t, 2, "123456789s1234z"),
			copies(t, 3, "123456789s1234z"),
			slices.Concat(copies(t, 1, "123456789m12p"), copies(t, 2, "55p")),
		},
		draws: []tile.TileID{copyOf(t, 0, "7z"), copyOf(t, 1, "7z"), copyOf(t, 3, "3p")},
	}
}

func scoreTotal(scores [tile.SeatCount]int) int {
	total := 0
	for _, score := range scores {
		total += score
	}
	return total
}

func assertEqual[T any](t *testing.T, what string, got, want T) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s mismatch (-got +want):\n%s", what, cmp.Diff(got, want, cmp.Exporter(func(reflect.Type) bool { return true })))
	}
}

func assertSameGame(t *testing.T, what string, got, want engine.Game) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("%s: the games differ (-got +want):\n%s", what, cmp.Diff(got, want, cmp.Exporter(func(reflect.Type) bool { return true })))
	}
}
